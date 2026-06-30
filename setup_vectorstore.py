"""
Uploads the synthetic policies to an OpenAI vector store (file search)
and saves the VECTOR_STORE_ID into the .env file.

Usage:
    python setup_vectorstore.py

Requires OPENAI_API_KEY in the environment or in .env.
"""

from __future__ import annotations

import glob
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

ROOT = Path(__file__).parent
POLICIES_DIR = ROOT / "synthetic_data" / "policies"
ENV_PATH = ROOT / ".env"


def upsert_env(key: str, value: str) -> None:
    """Write or update KEY=value in .env without touching the rest."""
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}=", line):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY missing. Copy .env.example to .env and set your key."
        )

    client = OpenAI()

    files = sorted(glob.glob(str(POLICIES_DIR / "*.txt")))
    if not files:
        raise SystemExit(f"No policies found in {POLICIES_DIR}")

    print(f"Creating vector store with {len(files)} policies...")
    vector_store = client.vector_stores.create(name="claimpilot-policies")

    streams = [open(f, "rb") for f in files]
    try:
        batch = client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store.id,
            files=streams,
        )
    finally:
        for s in streams:
            s.close()

    print(f"Batch status: {batch.status}")
    print(f"Files processed: {batch.file_counts.completed}/{batch.file_counts.total}")

    upsert_env("VECTOR_STORE_ID", vector_store.id)
    print(f"\nVECTOR_STORE_ID saved to .env: {vector_store.id}")
    print("Done. You can now run:  python server.py")


if __name__ == "__main__":
    main()
