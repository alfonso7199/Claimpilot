"""
Cheap pre-demo smoke test for ClaimPilot.

It checks only local endpoints that do not call OpenAI, so it is safe to run
before a live demo without spending API credits.

Usage:
    python server.py
    python scripts/demo_smoke.py
"""

from __future__ import annotations

import json
import sys
from urllib.error import URLError
from urllib.request import urlopen


BASE_URL = "http://127.0.0.1:8000"
EXPECTED_EXAMPLES = {
    "01_auto_complete",
    "02_home_complete",
    "03_missing_policy_number",
    "04_suspected_fraud",
}


def get_json(path: str) -> dict | list:
    with urlopen(BASE_URL + path, timeout=5) as res:  # noqa: S310 - local demo URL
        return json.loads(res.read().decode("utf-8"))


def get_text(path: str) -> str:
    with urlopen(BASE_URL + path, timeout=5) as res:  # noqa: S310 - local demo URL
        return res.read().decode("utf-8", errors="replace")


def main() -> int:
    try:
        health = get_json("/api/health")
        examples = get_json("/api/examples")
        html = get_text("/")
    except URLError as exc:
        print(f"ERROR: ClaimPilot server is not reachable at {BASE_URL}: {exc}")
        return 1

    missing = sorted(EXPECTED_EXAMPLES - set(examples))
    checks = {
        "home_page": "ClaimPilot" in html,
        "openai_key_configured": bool(health.get("openai_key")),
        "vector_store_configured": bool(health.get("vector_store")),
        "examples_present": not missing,
    }

    for name, ok in checks.items():
        print(f"{'OK' if ok else 'FAIL'} {name}")

    if missing:
        print("Missing examples: " + ", ".join(missing))

    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
