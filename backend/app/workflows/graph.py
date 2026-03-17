"""LangGraph workflow assembly and compilation.

WHAT IS LANGGRAPH?
───────────────────
LangGraph is a library for building stateful, multi-step AI workflows as
directed graphs. Each node in the graph is a Python function that receives
the current WorkflowState and returns a dict of fields to update.

Edges define execution order. Conditional edges let a routing function
choose which node to go to next — this is how the retry loop works.

THE DOCFORGE WORKFLOW
──────────────────────
Normal path (no validation errors):

  parse ──► chunk ──► extract ──► validate ──► merge ──► END
    │          │          │           │           │
  Load       Split      Call        Check       Combine
  file       into       LLM per     required    chunks
  to text    chunks     chunk       fields      into one
                                                result

Retry path (validation found missing required fields):

  extract ◄────────────────────────────────────────────┐
                                                         │
  parse ──► chunk ──► extract ──► validate ──► [retry?] ─┘
                                       │
                                       └──► merge ──► END  (if clean or max retries hit)

route_after_validate decides which path to take:
  - no errors         → go to "merge" (done)
  - errors + retries  → go back to "extract" (retry with error context in prompt)
  - errors + maxed    → go to "merge" anyway (best-effort result)

WHY COMPILE ONCE?
──────────────────
`graph.compile()` validates the graph structure (no dangling edges, no missing
nodes) and builds the internal execution engine. This is expensive, so we do it
once at module import time and store the result as `compiled_graph`. Every
request reuses the same compiled graph — only the state differs per run.
"""

from langgraph.graph import END, StateGraph

from app.workflows.nodes import (
    chunk_text,
    extract_structured,
    merge_extractions,
    parse_document,
    validate_extraction,
)
from app.workflows.state import WorkflowState


def route_after_validate(state: WorkflowState) -> str:
    """Decide whether to retry extraction or proceed to merge.

    Returns the name of the next node to execute.
    LangGraph calls this function after every `validate` node execution.
    """
    if not state.last_validation_errors:
        # All required fields present — we're done
        return "merge"
    if state.retry_count <= state.max_retries:
        # Still have retries left — go back to extract with error context
        return "extract"
    # Exhausted retries — proceed to merge with whatever we have
    return "merge"


# ── Graph definition ──────────────────────────────────────────────────────────
# Build the graph by registering nodes then connecting them with edges.

graph: StateGraph[WorkflowState] = StateGraph(WorkflowState)

# Register each node: name → async function
graph.add_node("parse", parse_document)
graph.add_node("chunk", chunk_text)
graph.add_node("extract", extract_structured)
graph.add_node("validate", validate_extraction)
graph.add_node("merge", merge_extractions)

# Set the first node that runs when the graph is invoked
graph.set_entry_point("parse")

# Fixed edges: always go from A to B
graph.add_edge("parse", "chunk")
graph.add_edge("chunk", "extract")
graph.add_edge("extract", "validate")

# Conditional edge: after "validate", call route_after_validate to choose next node.
# The dict maps possible return values to node names.
graph.add_conditional_edges(
    "validate",
    route_after_validate,
    {"merge": "merge", "extract": "extract"},
)

# merge is the last step before the graph terminates
graph.add_edge("merge", END)

# ── Compile ───────────────────────────────────────────────────────────────────
# Validate the graph and build the execution engine. Module-level singleton —
# imported and called by app/services/extraction.py for every request.
compiled_graph = graph.compile()
