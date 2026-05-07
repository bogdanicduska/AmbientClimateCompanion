"""End-to-end intent-routing harness for /speech/ask.

For every intent in backend/app/data/intents.json, sends each example
utterance to the running backend and checks that the LLM tagged it with
the expected intent. Prints a per-intent pass/fail summary plus the
exact answers — handy for the defense demo and for catching regressions
when you tune the system prompt.

Run with the backend already up:
    python -m scripts.test_intents
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL  = os.getenv("ASK_URL", "http://127.0.0.1:8080/api/v1/speech/ask")
TOKEN     = os.getenv("DEVICE_AUTH_TOKEN", "changeme")
DEVICE_ID = os.getenv("TEST_DEVICE_ID", "m5stack-ana-home")
HEADERS   = {"Authorization": f"Bearer {TOKEN}"}

INTENTS_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "data" / "intents.json"
)


def _ask(question: str) -> dict:
    r = requests.post(
        BASE_URL,
        json={"device_id": DEVICE_ID, "question": question},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"backend returned success=False: {body}")
    return body["data"]


def main() -> int:
    catalog = json.loads(INTENTS_PATH.read_text(encoding="utf-8"))
    intents = catalog["intents"]

    results = defaultdict(lambda: {"pass": 0, "fail": 0, "rows": []})
    overall_pass = overall_fail = 0

    for intent in intents:
        intent_id = intent["id"]
        examples  = intent.get("examples", [])
        if not examples:
            print(f"[skip] {intent_id}: no examples in intents.json")
            continue

        print(f"\n=== {intent_id} ({len(examples)} utterances) ===")
        for utterance in examples:
            try:
                data = _ask(utterance)
            except Exception as exc:
                print(f"  ERROR  '{utterance}' -> {exc}")
                results[intent_id]["fail"] += 1
                overall_fail += 1
                continue

            got    = data.get("intent")
            answer = (data.get("answer") or "").strip()
            ok     = got == intent_id
            mark   = "PASS" if ok else "FAIL"

            print(f"  {mark}  '{utterance}'")
            print(f"        got    = {got}")
            print(f"        answer = {answer}")

            results[intent_id]["pass" if ok else "fail"] += 1
            results[intent_id]["rows"].append((utterance, got, answer, ok))
            overall_pass += int(ok)
            overall_fail += int(not ok)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for intent_id, r in results.items():
        total = r["pass"] + r["fail"]
        print(f"  {intent_id:20s} {r['pass']:>2d}/{total} pass")
    print(f"\n  TOTAL                {overall_pass:>2d}/{overall_pass + overall_fail} pass")

    return 0 if overall_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
