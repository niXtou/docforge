"""LangGraph workflow assembly and compilation."""

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
    """Route to merge (done/max-retries) or back to extract (retry)."""
    if not state.last_validation_errors:
        return "merge"
    if state.retry_count <= state.max_retries:
        return "extract"
    return "merge"


graph: StateGraph[WorkflowState] = StateGraph(WorkflowState)
graph.add_node("parse", parse_document)
graph.add_node("chunk", chunk_text)
graph.add_node("extract", extract_structured)
graph.add_node("validate", validate_extraction)
graph.add_node("merge", merge_extractions)

graph.set_entry_point("parse")
graph.add_edge("parse", "chunk")
graph.add_edge("chunk", "extract")
graph.add_edge("extract", "validate")
graph.add_conditional_edges(
    "validate",
    route_after_validate,
    {"merge": "merge", "extract": "extract"},
)
graph.add_edge("merge", END)

compiled_graph = graph.compile()
