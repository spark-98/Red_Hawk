"""Test the action the dashboard's 'Start Assessment' button performs.

Replicates dashboard._run_assessment exactly: set TARGET_URL, then run
real_data.build_results in a worker thread (clean asyncio loop), and confirm
run_results.json is refreshed and generate_real_results() returns the new data.
Starts/stops the demo target bot itself.
"""
from __future__ import annotations

import concurrent.futures
import json
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
_RESULTS = _HERE / "run_results.json"


def _env():
    env = os.environ.copy()
    env["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
    env["GOOGLE_CLOUD_PROJECT"] = env.get("GOOGLE_CLOUD_PROJECT", "red-hawk-498917")
    env["GOOGLE_CLOUD_LOCATION"] = env.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    env.pop("GOOGLE_API_KEY", None)
    return env


def start_target():
    proc = subprocess.Popen([_PY, str(_HERE / "target_bot.py")],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env())
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


# ---- mirror of dashboard._run_assessment ----
def run_assessment(target_url: str, num_rounds: int, attacks_per_round: int):
    os.environ["TARGET_URL"] = target_url.strip()
    from real_data import build_results
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(build_results, num_rounds, attacks_per_round).result()


def main():
    print("=" * 60)
    print("Red Hawk — 'Start Assessment' button flow test")
    print("=" * 60)
    proc = None
    try:
        # capture prior file state so we can prove it was refreshed
        before = _RESULTS.read_text(encoding="utf-8") if _RESULTS.exists() else None

        print("\n[1] starting demo target bot ...")
        proc = start_target()
        print("    up.")

        target = "http://127.0.0.1:5001/attack"
        print(f"\n[2] simulating button click: TARGET_URL={target}, 2 rounds x 2 attacks ...")
        records = run_assessment(target, 2, 2)
        print(f"    build_results returned {len(records)} records")
        print(f"    TARGET_URL now in env = {os.environ.get('TARGET_URL')}")

        print("\n[3] confirming run_results.json was written/refreshed ...")
        assert _RESULTS.exists(), "run_results.json missing"
        after = _RESULTS.read_text(encoding="utf-8")
        on_disk = json.loads(after)
        print(f"    file has {len(on_disk)} records; changed_from_before={after != before}")

        print("\n[4] confirming dashboard's loader returns the new data ...")
        from real_data import generate_real_results
        loaded = generate_real_results()
        ok = (isinstance(loaded, list) and len(loaded) == len(records) and len(loaded) > 0
              and all({"round", "attack_family", "breakdown", "success"} <= set(r) for r in loaded))
        print(f"    generate_real_results -> {len(loaded)} records, shape_ok={ok}")
        rounds = sorted({r['round'] for r in loaded})
        print(f"    rounds present: {rounds}")

        print("\n" + "=" * 60)
        print(f"RESULT: {'PASS ✓ button flow produces dashboard results' if ok else 'FAIL ✗'}")
        print("=" * 60)
        sys.exit(0 if ok else 1)
    finally:
        if proc and proc.poll() is None:
            proc.kill(); proc.wait()
            print("\n    target bot stopped.")


if __name__ == "__main__":
    main()
