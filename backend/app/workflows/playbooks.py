"""Document-type playbooks and JSON-Schema extension-key handling.

WHY THIS MODULE EXISTS
───────────────────────
When a user picks "Research Paper" in the UI, the *application* knows the
document type — but the LLM never does. The extraction prompt historically
contained only the raw JSON Schema and the document text, so the model had no
way to know that `authors` means the byline on page 1 rather than a name in the
references. The result was hallucinated / mis-attributed values.

A *playbook* turns that type knowledge into explicit instructions the model
actually reads. Each schema can declare its type via the JSON-Schema extension
key ``x-doc-type``; ``build_system_prompt`` looks the type up here and assembles
a system prompt = universal base rules + the type-specific disambiguation block.

``x-*`` keys are a JSON-Schema convention for custom extensions, so a tagged
schema is still valid. But they are *our* metadata, not something the model API
should receive — ``strip_extension_keys`` removes them before the schema is
handed to ``with_structured_output``.
"""

from copy import deepcopy
from typing import Any

# Universal rules prepended to every extraction prompt. These are the
# anti-hallucination guardrails that apply no matter the document type.
BASE_SYSTEM_PROMPT = (
    "You are a precise document-extraction engine. Extract structured data from "
    "the document into the requested schema.\n\n"
    "Rules:\n"
    "1. Extract ONLY values that are explicitly present in the document.\n"
    "2. If a field's value is not present, return null for it. Do NOT infer, "
    "guess, fabricate, or use outside knowledge.\n"
    "3. Treat each field's description as the authoritative instruction for what "
    "to extract and where to find it.\n"
    "4. Copy values faithfully from the source; do not paraphrase identifiers, "
    "names, numbers, or dates.\n"
)

# Per-type disambiguation blocks. Keyed by the value of the schema's
# ``x-doc-type`` extension key. Keep each block short and concrete — these are
# the rules that resolve the specific confusions seen in production.
PLAYBOOKS: dict[str, str] = {
    "research_paper": (
        "This document is an academic research paper.\n"
        "- 'authors' are the byline listed directly under the title on the first "
        "page. NEVER include names that appear in the references, citations, "
        "bibliography, or acknowledgements — those are other people's work.\n"
        "- 'title' is the paper's own title at the top, not a cited work's title "
        "or a section heading.\n"
    ),
    "resume": (
        "This document is a resume / CV.\n"
        "- 'full_name' is the name of the person the resume belongs to — usually "
        "the most prominent text at the top. It is NOT a reference, a previous "
        "employer, a manager, or a school name.\n"
        "- Contact fields (email, phone, links) belong to that same person.\n"
    ),
    "invoice": (
        "This document is an invoice.\n"
        "- 'vendor_name' is the party who ISSUED the invoice (the seller / "
        "biller), not the customer being billed.\n"
        "- Amounts and the currency must be copied exactly as printed.\n"
    ),
    "generic": (
        "Follow each field's description carefully and extract only what the document supports.\n"
    ),
}


def build_system_prompt(doc_type: str | None) -> str:
    """Assemble the extraction system prompt for a given document type.

    Returns the universal base rules followed by the type-specific playbook.
    Unknown or missing ``doc_type`` falls back to the ``generic`` playbook.
    """
    playbook = PLAYBOOKS.get(doc_type or "generic", PLAYBOOKS["generic"])
    return f"{BASE_SYSTEM_PROMPT}\n{playbook}"


def strip_extension_keys(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``schema`` with top-level ``x-*`` keys removed.

    The model API only needs the standard JSON-Schema fields; our ``x-doc-type``
    (and any future ``x-*`` metadata) would otherwise be sent needlessly. The
    input is not mutated.
    """
    cleaned = deepcopy(schema)
    for key in [k for k in cleaned if k.startswith("x-")]:
        del cleaned[key]
    return cleaned
