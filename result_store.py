"""JSON storage of structured results (Stage 36, spec §3, §8).

A project stores, next to each run's report, the structured result it
was built from, so that numbers, tables and figures can be shown again
after a restart without recalculating and without parsing report text.
"""

from __future__ import annotations


def _kinds():
    from batch_correlation import CorrelationFamily
    from batch_groups import GroupFamily, TwoGroupFamily
    from stat_results import StructuredResult

    return {"structured": StructuredResult, "correlation_family": CorrelationFamily,
            "group_family": GroupFamily, "two_group_family": TwoGroupFamily}


def to_json(result) -> dict | None:
    """``{"kind": ..., "data": ...}`` for a storable result, else None."""
    if result is None:
        return None
    for kind, cls in _kinds().items():
        if isinstance(result, cls):
            return {"kind": kind, "data": result.to_dict()}
    return None


def from_json(payload: dict | None):
    """The result object stored by :func:`to_json` (None if unknown)."""
    if not payload:
        return None
    cls = _kinds().get(payload.get("kind"))
    if cls is None:
        return None
    try:
        return cls.from_dict(payload["data"])
    except (KeyError, TypeError, ValueError):
        return None
