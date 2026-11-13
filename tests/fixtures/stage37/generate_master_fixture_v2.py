#!/usr/bin/env python3
"""Invented master-level study data, version 2. No participant data or instrument text.

Stage 37 (independent review S6). The owner's v1 (``generate_master_fixture.py``)
is unchanged. Version 2 adds what v1 cannot show:

* consistent mediation: X → M → Y where the indirect and the direct path
  have the same sign (the avoidance-like dimension M is tied negatively
  to Y, so a·b < 0 and c′ < 0);
* a coping dimension tied negatively to Y (avoidance-like) next to one
  tied positively (assertive-like);
* covariate effects of age, sex and employment on Y;
* reverse-keyed items, with the scoring key stated in the spec JSON;
* patterned missingness that depends on observed values (younger cases
  miss a coping item more often; unemployed cases a support item).

Uses only the Python standard library. The latent data-generating
coefficients are NOT fitted sample coefficients, and nothing here is an
empirical finding.

python tests/fixtures/stage37/generate_master_fixture_v2.py --out-dir .stage37-fixtures
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

N = 240
SEED = 37022026
LON_ITEMS, SUP_ITEMS, WELL_ITEMS, COPE_ITEMS = 10, 8, 5, 6
LON_REVERSE = (3, 7)            # 1-based, keyed in the opposite direction (1..4)
AVOID_REVERSE = (4,)            # 1-based (1..5)


def bounded(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, round(value)))


def generate(out_dir: Path) -> tuple[Path, Path]:
    rng = random.Random(SEED)
    rows: list[dict] = []
    for idx in range(N):
        age = rng.randint(18, 30)
        sex = rng.choice([0, 1, 2])
        employed = rng.choice([0, 1])
        x, w = rng.gauss(0, 1), rng.gauss(0, 1)
        avoid = 0.45 * x + 0.20 * x * w + rng.gauss(0, 0.85)
        assertive = -0.30 * x + rng.gauss(0, 0.9)
        y = (-0.30 * x - 0.35 * avoid + 0.25 * assertive + 0.20 * w
             + 0.15 * (age - 24) / 4 + 0.25 * employed + 0.15 * (sex == 1)
             + rng.gauss(0, 0.8))
        row = {"participant_code": f"FAKE2_{idx + 1:04d}", "age_years": age, "sex_code": sex,
               "employed_code": employed}
        loneliness = []
        for j in range(1, LON_ITEMS + 1):
            keyed = bounded(2.4 + 0.6 * x + rng.gauss(0, 0.7), 1, 4)
            loneliness.append(5 - keyed if j in LON_REVERSE else keyed)
        support = [bounded(4 + w + rng.gauss(0, 1.05), 1, 7) for _ in range(SUP_ITEMS)]
        wellbeing = [bounded(2.5 + 0.75 * y + rng.gauss(0, 0.8), 0, 5)
                     for _ in range(WELL_ITEMS)]
        avoidance = []
        for j in range(1, COPE_ITEMS + 1):
            keyed = bounded(3 + 0.7 * avoid + rng.gauss(0, 0.8), 1, 5)
            avoidance.append(6 - keyed if j in AVOID_REVERSE else keyed)
        assertion = [bounded(3 + 0.7 * assertive + rng.gauss(0, 0.8), 1, 5)
                     for _ in range(COPE_ITEMS)]
        for prefix, values in (("SYN2_LON", loneliness), ("SYN2_SUP", support),
                               ("SYN2_WELL", wellbeing), ("SYN2_AVOID", avoidance),
                               ("SYN2_ASSERT", assertion)):
            row.update({f"{prefix}_{j:02d}": v for j, v in enumerate(values, 1)})
        # Patterned missingness, drawn after the answers (it never changes them).
        if rng.random() < (0.20 if age < 21 else 0.03):
            row["SYN2_AVOID_02"] = ""
        if rng.random() < (0.08 if employed == 0 else 0.02):
            row["SYN2_SUP_05"] = ""
        rows.append(row)
    for row in rows:
        lon = [row[f"SYN2_LON_{j:02d}"] for j in range(1, LON_ITEMS + 1)]
        keyed = [5 - v if j in LON_REVERSE else v for j, v in enumerate(lon, 1)]
        row["SYN2_LON_TOTAL"] = sum(keyed)
        sup = [row[f"SYN2_SUP_{j:02d}"] for j in range(1, SUP_ITEMS + 1)]
        row["SYN2_SUP_MEAN"] = "" if "" in sup else round(sum(sup) / SUP_ITEMS, 6)
        row["SYN2_WELL_0_100"] = 4 * sum(row[f"SYN2_WELL_{j:02d}"]
                                         for j in range(1, WELL_ITEMS + 1))
        avoid = [row[f"SYN2_AVOID_{j:02d}"] for j in range(1, COPE_ITEMS + 1)]
        keyed = [6 - v if (v != "" and j in AVOID_REVERSE) else v
                 for j, v in enumerate(avoid, 1)]
        row["SYN2_AVOID_MEAN"] = "" if "" in keyed else round(sum(keyed) / COPE_ITEMS, 6)
        row["SYN2_ASSERT_MEAN"] = round(sum(row[f"SYN2_ASSERT_{j:02d}"]
                                            for j in range(1, COPE_ITEMS + 1)) / COPE_ITEMS, 6)
    columns = list(rows[0])
    for extra in ("SYN2_LON_TOTAL", "SYN2_SUP_MEAN", "SYN2_WELL_0_100", "SYN2_AVOID_MEAN",
                  "SYN2_ASSERT_MEAN"):
        if extra not in columns:
            columns.append(extra)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "synthetic_master_research_v2_n240.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    spec = {
        "notice": "Synthetic fixture v2 ONLY: no real people, questions or validated keys",
        "version": 2, "seed": SEED, "n": N, "columns": len(columns),
        "X": "SYN2_LON_TOTAL (10 fictional 1..4 items; items 3 and 7 reverse-keyed)",
        "M": "SYN2_AVOID_MEAN (6 fictional 1..5 items; item 4 reverse-keyed)",
        "W": "SYN2_SUP_MEAN (8 fictional 1..7 items)",
        "Y": "SYN2_WELL_0_100 (5 fictional 0..5 items; sum times 4)",
        "second_dimension": "SYN2_ASSERT_MEAN (6 fictional 1..5 items)",
        "scoring_key": {
            "SYN2_LON_TOTAL": {"items": [f"SYN2_LON_{j:02d}" for j in range(1, LON_ITEMS + 1)],
                               "reverse": [f"SYN2_LON_{j:02d}" for j in LON_REVERSE],
                               "reverse_rule": "5 - answer", "score": "sum"},
            "SYN2_AVOID_MEAN": {"items": [f"SYN2_AVOID_{j:02d}"
                                          for j in range(1, COPE_ITEMS + 1)],
                                "reverse": [f"SYN2_AVOID_{j:02d}" for j in AVOID_REVERSE],
                                "reverse_rule": "6 - answer", "score": "mean"}},
        "latent_model": {
            "M": "0.45*X+0.20*X*W+N(0,0.85)",
            "assertive": "-0.30*X+N(0,0.9)",
            "Y": "-0.30*X-0.35*M+0.25*assertive+0.20*W+0.15*(age-24)/4+0.25*employed"
                 "+0.15*[sex==1]+N(0,0.8)"},
        "missing": {"SYN2_AVOID_02": "probability 0.20 if age < 21, else 0.03",
                    "SYN2_SUP_05": "probability 0.08 if employed == 0, else 0.02"},
        "warning": "Latent parameters are not observed-score OLS coefficients. Independent "
                   "oracles must estimate all sample statistics; the synthetic model provides "
                   "no empirical scientific findings.",
        "validated_instrument": False,
        "has_private_source_data": False,
    }
    spec_path = out_dir / "synthetic_master_model_spec_v2.json"
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return csv_path, spec_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=".stage37-fixtures")
    args = parser.parse_args()
    for path in generate(Path(args.out_dir)):
        print(f"{path}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
