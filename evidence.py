"""
Multimodal evidence ingestion for ClaimPilot.

Claims arrive in many shapes: a free-text email, a call recording, a photo of the
damage, a scanned PDF form. This module normalizes ANY of them into plain text
(a "claim dossier") that the agent pipeline can reason over.

  - .txt / .eml / .md      -> read as text
  - .pdf                   -> extract text; if scanned (no text layer), render the
                              pages to images and read them with a vision model
  - .png / .jpg / .webp    -> vision model extracts claim-relevant info
  - .mp3 / .wav / .m4a ...  -> audio transcription

All OpenAI calls are synchronous; callers run them in a thread to stay async.
100% synthetic data. Do not use with real information.
"""

from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass
from typing import Callable, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

VISION_MODEL = os.getenv("CLAIMPILOT_VISION_MODEL", "gpt-4o")
TRANSCRIBE_MODEL = os.getenv("CLAIMPILOT_TRANSCRIBE_MODEL", "gpt-4o-transcribe")

TEXT_EXT = {".txt", ".eml", ".md", ".text"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".oga", ".webm", ".mp4", ".mpga", ".flac"}
PDF_EXT = {".pdf"}

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

VISION_PROMPT = (
    "This image is evidence for an insurance claim. It may be a photo of damage "
    "(vehicle, property) or a scanned/photographed document (claim form, report, "
    "policy). Extract ALL claim-relevant information as plain text: visible damage, "
    "any printed or handwritten text, policy numbers, dates, names, amounts and "
    "locations. Be faithful to what is shown; do not invent details."
)


@dataclass
class EvidenceItem:
    name: str
    kind: str  # "text" | "audio transcript" | "image analysis" | "pdf" | "pdf (scanned)"
    text: str


def _client() -> OpenAI:
    return OpenAI()


def transcribe_audio(name: str, data: bytes) -> str:
    client = _client()
    try:
        res = client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=(name, data),
        )
    except Exception:
        # Fallback to the widely-available Whisper model
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=(name, data),
        )
    return res.text.strip()


def image_to_text(data: bytes, mime: str = "image/png") -> str:
    client = _client()
    b64 = base64.b64encode(data).decode("ascii")
    res = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
    )
    return (res.choices[0].message.content or "").strip()


def pdf_to_text(data: bytes) -> tuple[str, bool]:
    """Return (text, was_scanned). Falls back to vision for image-only PDFs."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    text_parts = [page.get_text().strip() for page in doc]
    joined = "\n".join(t for t in text_parts if t).strip()

    if len(joined) >= 40:
        return joined, False

    # Scanned / image-only PDF -> render pages and read with vision
    vision_parts: list[str] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=180)
        png = pix.tobytes("png")
        vision_parts.append(f"[Page {i + 1}]\n" + image_to_text(png, "image/png"))
    return "\n\n".join(vision_parts).strip(), True


def extract_evidence(
    name: str,
    data: bytes,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> EvidenceItem:
    """Normalize one uploaded file into an EvidenceItem (text)."""
    if not data:
        return EvidenceItem(name, "empty", "")
    ext = os.path.splitext(name.lower())[1]

    def notify(status: str) -> None:
        if on_progress:
            on_progress("EvidenceIntake", status)

    if ext in TEXT_EXT:
        notify(f"Reading text from {name}...")
        return EvidenceItem(name, "text", data.decode("utf-8", errors="ignore").strip())

    if ext in AUDIO_EXT:
        notify(f"Transcribing audio {name}...")
        return EvidenceItem(name, "audio transcript", transcribe_audio(name, data))

    if ext in IMAGE_EXT:
        notify(f"Analyzing image {name}...")
        return EvidenceItem(name, "image analysis", image_to_text(data, _MIME.get(ext, "image/png")))

    if ext in PDF_EXT:
        notify(f"Reading PDF {name}...")
        text, scanned = pdf_to_text(data)
        return EvidenceItem(name, "pdf (scanned)" if scanned else "pdf", text)

    # Unknown extension: best-effort decode as text
    notify(f"Reading {name}...")
    return EvidenceItem(name, "text", data.decode("utf-8", errors="ignore").strip())


def build_dossier(items: list[EvidenceItem]) -> str:
    """Combine evidence items into a single annotated claim dossier."""
    if not items:
        return ""
    blocks = []
    for it in items:
        if not it.text:
            continue
        blocks.append(f"=== EVIDENCE: {it.name} ({it.kind}) ===\n{it.text}")
    return "\n\n".join(blocks)
