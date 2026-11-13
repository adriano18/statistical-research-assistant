#!/usr/bin/env python3
"""Invented master-level study data. No original participant data/instrument text.

Uses only Python stdlib. Output includes 20+52+5+12 FICTIONAL item columns,
four synthetic construct scores, demographics and controlled missingness.
The latent data-generating coefficients are NOT fitted sample coefficients.

python tests/fixtures/stage37/generate_master_fixture.py --out-dir .stage37-fixtures
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

N = 180
SEED = 37012026


def bounded(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, round(value)))


def generate(out_dir: Path) -> tuple[Path, Path]:
    rng = random.Random(SEED)
    rows: list[dict] = []
    for idx in range(N):
        x, w = rng.gauss(0, 1), rng.gauss(0, 1)
        m = 0.36*x + 0.18*x*w + rng.gauss(0, .9)
        y = -.45*x + .30*m + .25*w + .19*x*w + rng.gauss(0, .9)
        row = {
            "participant_code": f"FAKE_{idx+1:04d}",
            "age_years": rng.randint(18, 30),
            "sex_code": rng.choice([0, 1, 2]),
            "employed_code": rng.choice([0, 1]),
        }
        loneliness = [bounded(2.4 + .57*x + rng.gauss(0, .7), 1, 4)
                      for _ in range(20)]
        support = [bounded(4 + w + rng.gauss(0, 1.05), 1, 7)
                   for _ in range(12)]
        wellbeing = [bounded(2.5 + .75*y + rng.gauss(0, .8), 0, 5)
                     for _ in range(5)]
        coping: list[int] = []
        for group in range(8):
            factor = m if group == 0 else rng.gauss(0, .9) + ((group%3)-1)*.15*x
            for _ in range(7 if group < 4 else 6):
                coping.append(bounded(3 + .7*factor + rng.gauss(0, .85), 1, 5))
        assert len(coping) == 52
        for prefix, values in (
            ("SYN_LON", loneliness), ("SYN_SUP", support),
            ("SYN_WELL", wellbeing), ("SYN_COPE", coping)
        ):
            row.update({f"{prefix}_{j:02d}":val for j,val in enumerate(values,1)})
        row["SYN_LON_TOTAL"] = sum(loneliness)
        row["SYN_SUP_MEAN"] = round(sum(support)/12, 6)
        row["SYN_WELL_RAW"] = sum(wellbeing)
        row["SYN_WELL_0_100"] = sum(wellbeing)*4
        row["SYN_COPE_DIM1_MEAN"] = round(sum(coping[:7])/7, 6)
        if idx in (15, 82, 133):
            row["SYN_COPE_01"] = ""
            row["SYN_COPE_DIM1_MEAN"] = ""
        if idx in (45, 111):
            row["SYN_SUP_03"] = ""
            row["SYN_SUP_MEAN"] = ""
        rows.append(row)
    cols=list(rows[0])
    csv_path=out_dir/"synthetic_master_research_n180.csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer=csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    model={
        "notice": "Synthetic fixture ONLY: no real people, questions or validated keys",
        "seed": SEED, "n":N, "columns":len(cols),
        "X":"SYN_LON_TOTAL (20 fictional 1..4 items)",
        "M":"SYN_COPE_DIM1_MEAN (7 of 52 fictional 1..5 items)",
        "W":"SYN_SUP_MEAN (12 fictional 1..7 items)",
        "Y":"SYN_WELL_0_100 (5 fictional 0..5 items; sum times 4)",
        "latent_model":{
            "M":"0.36*X+0.18*X*W+N(0,0.9)",
            "Y":"-0.45*X+0.30*M+0.25*W+0.19*X*W+N(0,0.9)"
        },
        "missing":{
            "SYN_COPE_01": [16,83,134],
            "SYN_SUP_03": [46,112]
        },
        "warning": "Latent parameters are not observed-score OLS coefficients. Independent oracles must estimate all sample statistics; the synthetic model provides no empirical scientific findings.",
        "validated_instrument": False,
        "has_private_source_data": False
    }
    spec=out_dir/"synthetic_master_model_spec.json"
    spec.write_text(json.dumps(model,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return csv_path,spec


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",default=".stage37-fixtures")
    args=parser.parse_args()
    for p in generate(Path(args.out_dir)):
        print(f"{p}: {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
