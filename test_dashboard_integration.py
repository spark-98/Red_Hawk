"""End-to-end test: live pipeline -> Yanshi's judge -> dashboard-shaped records.

Starts the target bot, runs real_data.build_results against it, then validates that
every produced record exactly matches the keys/types/ranges dashboard.process_data
consumes. Mirrors process_data's field access so a pass guarantees the dashboard renders.

Run from D:\\Red_Hawk:
    gemini-hackathon\\.venv\\Scripts\\python.exe test_dashboard_integration.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent
_PY = sys.executable

_FAMILIES = {
    "jailbreak", "injection", "disclosure", "excessive_agency",
    "system_prompt_leakage", "misinformation", "output_manipulation",
}


def _env():
    env = os.environ.copy()
    env["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
    env["GOOGLE_CLOUD_PROJECT"] = env.get("GOOGLE_CLOUD_PROJECT", "red-hawk-498917")
    env["GOOGLE_CLOUD_LOCATION"] = env.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    env.pop("GOOGLE_API_KEY", None)
    return env


def start_target() -> subprocess.Popen:
    proc = subprocess.Popen(
        [_PY, str(_HERE / "target_bot.py")],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(),
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if requests.get("http://127.0.0.1:5001/health", timeout=2).status_code == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError("target bot did not start")


def validate(records: list) -> list[str]:
    """Return a list of problems; empty means the records are dashboard-ready."""
    problems: list[str] = []
    dims = ["groundedness", "recall", "severity_calibration", "actionability"]

    if not records:
        return ["no records produced"]

    for i, r in enumerate(records):
        tag = f"record[{i}]"
        # top-level keys process_data reads
        for k in ("round", "attack_family", "breakdown", "raw_total",
                  "final_total", "verdict", "success", "failure_reasons"):
            if k not in r:
                problems.append(f"{tag}: missing '{k}'")
        if problems:
            continue
        if not isinstance(r["round"], int):
            problems.append(f"{tag}: round not int")
        if r["attack_family"] not in _FAMILIES:
            problems.append(f"{tag}: unknown family {r['attack_family']!r}")
        if not isinstance(r["success"], bool):
            problems.append(f"{tag}: success not bool")
        if not (isinstance(r["raw_total"], int) and 0 <= r["raw_total"] <= 40):
            problems.append(f"{tag}: raw_total out of range: {r['raw_total']}")
        if not (isinstance(r["final_total"], int) and 0 <= r["final_total"] <= 40):
            problems.append(f"{tag}: final_total out of range: {r['final_total']}")
        if not isinstance(r["failure_reasons"], list):
            problems.append(f"{tag}: failure_reasons not list")

        bd = r["breakdown"]
        for d in dims:
            if d not in bd or "score" not in bd[d] or "reason" not in bd[d]:
                problems.append(f"{tag}: breakdown.{d} malformed")
                continue
            s = bd[d]["score"]
            if not (isinstance(s, int) and 0 <= s <= 10):
                problems.append(f"{tag}: breakdown.{d}.score out of range: {s}")
        sg = bd.get("safety_guardrail", {})
        if "pass" not in sg or "reason" not in sg:
            problems.append(f"{tag}: breakdown.safety_guardrail malformed")
        elif not isinstance(sg["pass"], bool):
            problems.append(f"{tag}: safety_guardrail.pass not bool")

        # consistency: final == raw when safety passed, else 0
        if sg.get("pass") is True and r["final_total"] != r["raw_total"]:
            problems.append(f"{tag}: final_total != raw_total despite safety pass")
        if sg.get("pass") is False and r["final_total"] != 0:
            problems.append(f"{tag}: final_total not zeroed despite safety fail")

    return problems


def simulate_process_data(records: list):
    """Run the SAME flatten + aggregation dashboard.process_data does, to prove it works."""
    import pandas as pd
    rows = []
    for item in records:
        bd = item["breakdown"]
        rows.append({
            "round": item["round"], "attack_family": item["attack_family"],
            "raw_total": item["raw_total"], "final_total": item["final_total"],
            "verdict": item["verdict"], "success": item["success"],
            "failure_reasons": ", ".join(item["failure_reasons"]) if item["failure_reasons"] else "None",
            "groundedness_score": bd["groundedness"]["score"],
            "recall_score": bd["recall"]["score"],
            "severity_score": bd["severity_calibration"]["score"],
            "actionability_score": bd["actionability"]["score"],
            "safety_pass": bd["safety_guardrail"]["pass"],
        })
    df = pd.DataFrame(rows)
    agg = df.groupby("round").agg(
        success_rate=("success", lambda x: x.sum() / len(x) * 100),
        avg_score=("final_total", "mean"),
    ).reset_index()
    return df, agg


def main() -> None:
    print("=" * 60)
    print("Red Hawk — Dashboard Integration Test")
    print("=" * 60)

    proc = None
    try:
        print("\n[1] Starting target bot on :5001 ...")
        proc = start_target()
        print("    target bot up.")

        print("\n[2] Running live pipeline (2 rounds x 2 attacks) ...")
        from real_data import build_results
        records = build_results(num_rounds=2, attacks_per_round=2)

        print("\n[3] Validating record shape against dashboard contract ...")
        problems = validate(records)
        if problems:
            print("    SHAPE PROBLEMS:")
            for p in problems:
                print(f"      - {p}")
        else:
            print(f"    OK — all {len(records)} records match the dashboard shape.")

        print("\n[4] Simulating dashboard.process_data + round aggregation ...")
        df, agg = simulate_process_data(records)
        print(f"    DataFrame: {len(df)} rows, {df['round'].nunique()} rounds, "
              f"{df['success'].sum()} successes")
        print("    Per-round (the 'success rate climbing' chart source):")
        for _, row in agg.iterrows():
            print(f"      round {int(row['round'])}: "
                  f"success_rate={row['success_rate']:.0f}%  "
                  f"avg_final={row['avg_score']:.1f}/40")

        ok = not problems
        print("\n" + "=" * 60)
        print(f"RESULT: {'PASS ✓ dashboard will render live data' if ok else 'FAIL ✗ shape mismatch'}")
        print("=" * 60)
        sys.exit(0 if ok else 1)
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
            print("\n    target bot stopped.")


if __name__ == "__main__":
    main()
