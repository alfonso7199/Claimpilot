"""
ClaimPilot - FastAPI backend.

Serves the custom web frontend and exposes:
  GET  /                      -> the web app
  GET  /api/examples          -> list of synthetic example claims
  GET  /api/example/{name}    -> text of one example
  POST /api/process           -> ingest evidence (text + files), start a job
  GET  /api/events/{job_id}   -> Server-Sent Events: live agent trace + result

Run:  python server.py     (or: uvicorn server:app --reload)
100% synthetic data. Do not use with real information.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, Header, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agents_pipeline import ClaimResult, finalize_claim, run_pipeline
from evidence import (
    AUDIO_EXT,
    IMAGE_EXT,
    PDF_EXT,
    TEXT_EXT,
    EvidenceItem,
    build_dossier,
    extract_evidence,
)

load_dotenv()

ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"
EMAILS_DIR = ROOT / "synthetic_data" / "emails"
OUTBOX = ROOT / "outbox"

MAX_FILE_MB = 25
MAX_FILES = 12
ACCEPTED_EXT = TEXT_EXT | IMAGE_EXT | AUDIO_EXT | PDF_EXT


def _example_path(name: str) -> Optional[Path]:
    """Resolve an example name to a file inside EMAILS_DIR, blocking traversal."""
    safe = Path(name.strip()).name  # drop any directory components
    if not safe:
        return None
    if not safe.endswith(".txt"):
        safe += ".txt"
    candidate = (EMAILS_DIR / safe).resolve()
    try:
        if candidate.parent == EMAILS_DIR.resolve() and candidate.exists():
            return candidate
    except OSError:
        return None
    return None


def _friendly_error(e: Exception) -> str:
    name = type(e).__name__
    msg = str(e)
    low = msg.lower()
    if name == "AuthenticationError" or "api key" in low or "api_key" in low:
        return "OpenAI rejected the API key. Check OPENAI_API_KEY in your .env file."
    if name == "RateLimitError" or "rate limit" in low or "quota" in low:
        return "OpenAI rate limit or quota reached. Add credit or wait a moment, then retry."
    if name in ("APITimeoutError", "APIConnectionError") or "timeout" in low:
        return "Could not reach OpenAI (network or timeout). Check your connection and retry."
    return f"{name}: {msg}"

app = FastAPI(title="ClaimPilot")

# In-memory job store: job_id -> asyncio.Queue of event dicts
JOBS: dict[str, asyncio.Queue] = {}


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------
def serialize(result: ClaimResult) -> dict:
    return {
        "needs_more_info": result.needs_more_info,
        "info_request_email": result.info_request_email,
        "intake": result.intake.model_dump() if result.intake else None,
        "coverage": result.coverage.model_dump() if result.coverage else None,
        "triage": result.triage.model_dump() if result.triage else None,
        "audit_log": [asdict(e) for e in result.audit_log],
    }


def _status_for(name: str) -> str:
    ext = os.path.splitext(name.lower())[1]
    if ext in AUDIO_EXT:
        return f"Transcribing audio: {name}"
    if ext in IMAGE_EXT:
        return f"Analyzing image: {name}"
    if ext in PDF_EXT:
        return f"Reading PDF: {name}"
    return f"Reading: {name}"


# --------------------------------------------------------------------------
# Background job
# --------------------------------------------------------------------------
def apply_key(key) -> None:
    """Use a per-request OpenAI key (from the UI) if provided; else keep .env."""
    if key:
        os.environ["OPENAI_API_KEY"] = key
        try:
            from agents import set_default_openai_key
            set_default_openai_key(key)
        except Exception:
            pass


async def run_job(job_id: str, text: str, example_texts: list[tuple[str, str]],
                  files: list[tuple[str, bytes]], key=None) -> None:
    q = JOBS[job_id]
    apply_key(key)

    def emit(etype: str, **kw) -> None:
        q.put_nowait({"type": etype, **kw})

    try:
        items: list[EvidenceItem] = []

        if text.strip():
            items.append(EvidenceItem("Pasted text", "text", text.strip()))
            emit("evidence", name="Pasted text", kind="text")

        for name, etext in example_texts:
            items.append(EvidenceItem(name, "example email", etext))
            emit("evidence", name=name, kind="example email")

        for name, data in files:
            ext = os.path.splitext(name.lower())[1]
            if not data:
                emit("evidence", name=name, kind="skipped (empty file)")
                continue
            if len(data) > MAX_FILE_MB * 1024 * 1024:
                emit("evidence", name=name, kind=f"skipped (over {MAX_FILE_MB} MB)")
                continue
            if ext and ext not in ACCEPTED_EXT:
                emit("evidence", name=name, kind="skipped (unsupported type)")
                continue
            emit("progress", agent="EvidenceIntake", status=_status_for(name))
            try:
                item = await asyncio.to_thread(extract_evidence, name, data)
            except Exception as ex:  # noqa: BLE001
                emit("evidence", name=name, kind="unreadable")
                emit("note", message=f"Could not read {name}: {type(ex).__name__}")
                continue
            if not (item.text or "").strip():
                emit("evidence", name=item.name, kind=f"{item.kind} (no content)")
                continue
            items.append(item)
            emit("evidence", name=item.name, kind=item.kind)

        dossier = build_dossier(items)
        if not dossier.strip():
            emit("error", message=(
                "No readable evidence found. Add a text claim, a clear photo or PDF, "
                "or an audio file."
            ))
            return

        # The pipeline's progress callback runs in this same event loop -> safe.
        def on_progress(agent: str, status: str) -> None:
            q.put_nowait({"type": "progress", "agent": agent, "status": status})

        result = await run_pipeline(dossier, on_progress=on_progress)
        emit("result", data=serialize(result), dossier=dossier)

    except Exception as e:  # noqa: BLE001
        emit("error", message=_friendly_error(e))
    finally:
        q.put_nowait(None)  # sentinel: stream end


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/api/examples")
async def list_examples() -> JSONResponse:
    names = sorted(p.stem for p in EMAILS_DIR.glob("*.txt"))
    return JSONResponse(names)


@app.get("/api/example/{name}")
async def get_example(name: str) -> JSONResponse:
    path = _example_path(name)
    if not path:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"name": path.stem, "text": path.read_text(encoding="utf-8")})


@app.post("/api/process")
async def process(
    text: str = Form(""),
    examples: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    x_openai_key: str = Header(None),
) -> JSONResponse:
    example_texts: list[tuple[str, str]] = []
    for name in [e for e in examples.split(",") if e.strip()]:
        path = _example_path(name)
        if path:
            example_texts.append((path.stem, path.read_text(encoding="utf-8")))

    file_blobs: list[tuple[str, bytes]] = []
    for f in files[:MAX_FILES]:
        if f.filename:
            file_blobs.append((f.filename, await f.read()))

    job_id = uuid.uuid4().hex
    JOBS[job_id] = asyncio.Queue()
    asyncio.create_task(run_job(job_id, text, example_texts, file_blobs, key=x_openai_key))
    return JSONResponse({"job_id": job_id})


@app.get("/api/events/{job_id}")
async def events(job_id: str) -> StreamingResponse:
    async def stream():
        q = JOBS.get(job_id)
        if q is None:
            yield f"data: {json.dumps({'type': 'error', 'message': 'unknown job'})}\n\n"
            return
        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            JOBS.pop(job_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/finalize")
async def finalize(payload: dict = Body(...), x_openai_key: str = Header(None)) -> JSONResponse:
    apply_key(x_openai_key)
    decision = (payload.get("decision") or "approved").lower()
    try:
        fin = await finalize_claim(
            payload.get("intake") or {},
            payload.get("coverage"),
            payload.get("triage"),
            decision,
            reviewer_note=payload.get("note") or "",
        )
        return JSONResponse(fin.model_dump())
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": _friendly_error(e)}, status_code=200)


@app.post("/api/ask")
async def ask(payload: dict = Body(...), x_openai_key: str = Header(None)) -> JSONResponse:
    apply_key(x_openai_key)
    question = (payload.get("question") or "").strip()
    dossier = payload.get("dossier") or ""
    if not question:
        return JSONResponse({"error": "Empty question."}, status_code=200)
    try:
        from agents_pipeline import answer_question

        answer = await answer_question(dossier, question)
        return JSONResponse({"answer": answer})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": _friendly_error(e)}, status_code=200)


@app.post("/api/outreach")
async def outreach(payload: dict = Body(...), x_openai_key: str = Header(None)) -> JSONResponse:
    """Simulated-but-traceable send: write the request to the outbox and log it."""
    apply_key(x_openai_key)
    recipient = (payload.get("recipient") or "unknown@customer").strip()
    message = payload.get("message") or ""
    OUTBOX.mkdir(exist_ok=True)
    now = datetime.now()
    ts = now.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c for c in recipient if c.isalnum() or c in "@.-_") or "customer"
    fname = f"{ts}_{safe}.txt"
    (OUTBOX / fname).write_text(
        f"To: {recipient}\nSent: {now.isoformat(timespec='seconds')}\n\n{message}\n",
        encoding="utf-8",
    )
    with (OUTBOX / "outreach_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "recipient": recipient, "file": fname}) + "\n")
    return JSONResponse({
        "ok": True,
        "recipient": recipient,
        "file": f"outbox/{fname}",
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "openai_key": bool(os.getenv("OPENAI_API_KEY")),
            "vector_store": bool(os.getenv("VECTOR_STORE_ID")),
        }
    )


# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
