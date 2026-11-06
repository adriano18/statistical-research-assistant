"""Windows CI: compare the startup of several packaged builds on ONE machine.

    python tools/startup_ab.py --variant baseline=a\\App.exe --variant cleaned=b\\App.exe \\
        --rounds 5 --out ab

Startup times measured on different CI runners differ by up to a second for
the same code, so before/after claims need both builds on the same runner.
Each round launches every variant once through ``check_gui_startup.py`` (the
normal startup path with a system-only PATH, screenshots and the app's own
startup record); the order alternates between rounds so that disk-cache
warm-up does not favour one variant. The first launch of each variant is
reported separately as the cold start.

Writes ``ab/startup-ab.json`` and ``ab/startup-ab.md`` (also printed).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
import subprocess
import sys

CHECK = Path(__file__).resolve().parent / "check_gui_startup.py"
METRICS = ("window_visible_after_s", "interface_ready_reported_s")


def run_once(exe: Path, out: Path, timeout: float) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, str(CHECK), str(exe), str(out), "--timeout", str(timeout)],
        capture_output=True, text=True, timeout=timeout + 120)
    result_path = out / "gui-startup-result.json"
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result = {"ok": False, "errors": [completed.stderr[-500:] or "no result written"]}
    result["exit_code"] = completed.returncode
    return result


def summarise(samples: dict[str, list[dict]]) -> dict:
    summary = {}
    for name, runs in samples.items():
        ok = [r for r in runs if r.get("ok")]
        entry = {"launches": len(runs), "ok": len(ok)}
        if ok:
            entry["cold"] = {m: ok[0].get(m) for m in METRICS}
            warm = ok[1:] or ok
            for metric in METRICS:
                values = [r[metric] for r in warm if isinstance(r.get(metric), (int, float))]
                if values:
                    entry[metric] = {"median": round(median(values), 3), "min": min(values),
                                     "max": max(values)}
        summary[name] = entry
    return summary


def to_markdown(summary: dict) -> str:
    lines = ["## Startup on one runner (alternating launches)", "",
             "| Build | OK launches | Cold: window / ready | Warm median: window / ready | Warm range ready |",
             "|---|---:|---:|---:|---:|"]
    for name, s in summary.items():
        cold = s.get("cold", {})
        window = s.get("window_visible_after_s", {})
        ready = s.get("interface_ready_reported_s", {})

        def seconds(value):
            return f"{value:.2f} s" if isinstance(value, (int, float)) else "—"

        lines.append(
            f"| {name} | {s['ok']}/{s['launches']} | "
            f"{seconds(cold.get('window_visible_after_s'))} / {seconds(cold.get('interface_ready_reported_s'))} | "
            f"{seconds(window.get('median'))} / {seconds(ready.get('median'))} | "
            f"{seconds(ready.get('min'))}–{seconds(ready.get('max'))} |")
    lines += ["", "Window visibility is sampled every 0.5 s; interface-ready is the app's own timer."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", action="append", required=True,
                        help="NAME=path\\to\\exe (repeat for every build)")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--out", type=Path, default=Path("startup-ab"))
    args = parser.parse_args(argv)

    variants = []
    for spec in args.variant:
        name, _, path = spec.partition("=")
        exe = Path(path)
        if not exe.is_file():
            print(f"Skipping {name}: {exe} does not exist", file=sys.stderr)
            continue
        variants.append((name, exe))
    samples: dict[str, list[dict]] = {name: [] for name, _ in variants}
    for round_number in range(1, args.rounds + 1):
        order = variants if round_number % 2 else list(reversed(variants))
        for name, exe in order:
            result = run_once(exe, args.out / name / f"round{round_number}", args.timeout)
            samples[name].append(result)
            print(f"round {round_number} {name}: ok={result.get('ok')} "
                  f"window={result.get('window_visible_after_s')} "
                  f"ready={result.get('interface_ready_reported_s')}", flush=True)
    summary = summarise(samples)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "startup-ab.json").write_text(
        json.dumps({"summary": summary, "samples": samples}, indent=1), encoding="utf-8")
    markdown = to_markdown(summary)
    (args.out / "startup-ab.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0 if all(s["ok"] == s["launches"] for s in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
