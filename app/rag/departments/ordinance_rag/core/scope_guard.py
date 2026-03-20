"""
ordinance_rag/core/scope_guard.py

Determines whether a user question is within scope for a given jurisdiction.
If out of scope, returns a polite refusal message instead of querying the RAG.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Out-of-scope patterns — fast keyword check before hitting the LLM
# ---------------------------------------------------------------------------

OUT_OF_SCOPE_KEYWORDS = [
    # Other jurisdictions by name
    "fayetteville", "hope mills", "raeford", "hoke county", "harnett",
    # Unrelated government services
    "tax bill", "property tax", "dmv", "social services", "sheriff",
    "utilities bill", "water bill", "trash pickup", "school",
    # Legal/financial advice
    "sue", "lawsuit", "attorney", "lawyer", "court", "settlement",
    # Completely unrelated topics
    "weather", "recipe", "sports", "news", "stock",
]

IN_SCOPE_KEYWORDS = [
    "subdivision", "ordinance", "plat", "setback", "easement", "lot",
    "zoning", "street", "road", "block", "acreage", "preliminary",
    "final plat", "variance", "buffer", "utility", "right-of-way",
    "section", "article", "regulation", "permit", "approval", "planning",
    "flood", "drainage", "stormwater", "parcel", "reid", "pin number",
    "dedication", "certificate", "surveyor", "engineer", "cul-de-sac",
    "driveway", "access", "sidewalk", "open space", "density",
]


def is_in_scope(question: str) -> bool:
    """
    Quick keyword-based scope check.
    Returns True if the question appears to be about planning/ordinance topics.
    Returns False if it clearly is not.
    """
    q_lower = question.lower()

    # Hard out-of-scope hits
    for kw in OUT_OF_SCOPE_KEYWORDS:
        if kw in q_lower:
            return False

    # If any in-scope keyword is present, it's likely valid
    for kw in IN_SCOPE_KEYWORDS:
        if kw in q_lower:
            return True

    # Ambiguous — let it through and let the LLM + system prompt handle it
    return True


def get_refusal_message(jurisdiction_display_name: str) -> str:
    """
    Returns the standard polite refusal for out-of-scope questions.
    """
    return (
        f"I'm only able to help with questions related to "
        f"{jurisdiction_display_name} ordinances and planning regulations. "
        f"For other topics, please contact the Cumberland County "
        f"Planning & Inspections office directly at (910) 678-7600, "
        f"or visit the Planning & Inspections department in person."
    )
