"""Multiple-comparison adjustment of a family of p-values (Stage 36, spec §5).

A family is the set of tests that answer one research question (for
example UCLA against eight coping scales). Raw p-values are never
changed: the adjusted values are returned separately, together with the
procedure and the number of tests, so a report can show both.

- Holm (1979) step-down, controls the familywise error rate:
  p(i)* = max over j <= i of min(1, (m - j + 1) p(j)) for sorted p(1..m).
- Benjamini–Hochberg (1995) step-up, controls the false discovery rate:
  p(i)* = min over j >= i of min(1, m p(j) / j).
- Bonferroni: min(1, m p).

The tests compare these formulas with statsmodels' ``multipletests`` as an
independent oracle (tests/test_stage36_engine.py).
"""

from __future__ import annotations

from dataclasses import dataclass
import math

PROCEDURES = {
    "holm": "Holm (1979) step-down; familywise error rate",
    "bh": "Benjamini–Hochberg (1995) step-up; false discovery rate",
    "bonferroni": "Bonferroni; familywise error rate",
    "none": "No adjustment (raw p-values only)",
}


@dataclass(frozen=True)
class Adjustment:
    procedure: str                 # key of PROCEDURES
    description: str
    family_size: int               # tests that produced a p-value
    adjusted: tuple[float | None, ...]   # aligned with the input; None where no p-value


def _check(pvalues) -> list[float | None]:
    checked: list[float | None] = []
    for p in pvalues:
        if p is None or (isinstance(p, float) and math.isnan(p)):
            checked.append(None)
            continue
        value = float(p)
        if not math.isfinite(value) or value < 0 or value > 1:
            raise ValueError("p-values must lie in [0, 1].")
        checked.append(value)
    return checked


def adjust(pvalues, procedure: str = "holm") -> Adjustment:
    """Adjusted p-values for one family; tests without a p-value (failed or
    not applicable) are left out of the family and stay None."""
    if procedure not in PROCEDURES:
        raise ValueError(f"Unknown adjustment: {procedure}")
    values = _check(pvalues)
    present = [(index, p) for index, p in enumerate(values) if p is not None]
    m = len(present)
    adjusted: list[float | None] = [None] * len(values)
    if procedure == "none" or m == 0:
        for index, p in present:
            adjusted[index] = p
        return Adjustment(procedure, PROCEDURES[procedure], m, tuple(adjusted))
    order = sorted(present, key=lambda item: item[1])
    if procedure == "bonferroni":
        for index, p in present:
            adjusted[index] = min(1.0, m * p)
    elif procedure == "holm":
        running = 0.0
        for rank, (index, p) in enumerate(order):          # rank 0 = smallest p
            running = max(running, min(1.0, (m - rank) * p))
            adjusted[index] = running
    else:                                                   # Benjamini–Hochberg
        running = 1.0
        for rank in range(m - 1, -1, -1):
            index, p = order[rank]
            running = min(running, min(1.0, m * p / (rank + 1)))
            adjusted[index] = running
    return Adjustment(procedure, PROCEDURES[procedure], m, tuple(adjusted))
