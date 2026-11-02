"""Small, transparent hints about variable roles.

Column-name heuristics are safeguards, not a substitute for researcher review.
"""


def looks_like_identifier(name: str) -> bool:
    """Recognize commonly named record/person identifiers."""
    normalized = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    return normalized == "id" or normalized.endswith("_id") or normalized in {
        "respondent", "participant_number", "respondent_number", "subject_number"
    }
