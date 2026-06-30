# ClaimPilot

**From any claim — a call, a photo, a PDF or an email — to an auditable claim file in minutes.**

ClaimPilot is an agentic First Notice of Loss (FNOL) assistant for insurers. It ingests a
claim in whatever form it arrives, extracts the structured facts, checks coverage against the
policy wording **with citations**, recommends a triage route, and prepares a decision-ready
claim file that a human approves, edits or escalates. Built with the **OpenAI Agents SDK** for
the HCLTech–OpenAI Agentic AI Hackathon (Track 1 — Industry / Business Transformation).

## The problem

A claim arrives as a free-text email, a phone call, a scanned form or a photo of the damage.
A handler has to read it, key in the data, find the policy, check what's covered and decide
where it goes — by hand, thousands of times. It is slow (often 26–48h to reach the right
adjuster), inconsistent, and a single missed clause is expensive.

## What it does

- **Multimodal intake** — drop an audio call, a photo/scan, a PDF or text; everything is
  normalized into one claim dossier (transcription, vision, document parsing).
- **Structured extraction** — policy number, dates, parties, damages, fraud signals, gaps.
- **Coverage with citations** — retrieves the relevant policy clauses and quotes them verbatim
  (OpenAI file search over a vector store), so every verdict is traceable.
- **Triage with reasons** — direct payment / adjuster / investigation, with a confidence score
  and explicit reasons to approve or decline.
- **Human in the loop** — approve, reject, **reopen**, **override the route**, **re-evaluate**
  with new information, or **ask questions** about the file; approval triggers a real downstream
  action (payment instruction, adjuster assignment, investigation) and a customer communication
  logged to an outbox and the audit trail.
- **Guardrail** — if triage confidence is below 0.7, human review is forced.

## How it works

```
audio / image / PDF / email
        │  (evidence intake: transcription · vision · parsing)
        ▼
   IntakeAgent  ──►  PolicyAgent  ──►  TriageAgent  ──►  Manager
  (structured)     (coverage +        (route +          (claim file +
                    cited clauses)     confidence)        audit log)
        │                                                   │
        └─ missing data → drafts an outreach request        └─► HUMAN: approve / reject /
                                                                 reopen / override / re-evaluate / ask
```

Six specialized agents: IntakeAgent, PolicyAgent, TriageAgent, an info-request/outreach agent,
an Action agent (downstream action on approval) and a Q&A agent over the assembled file.

## Tech stack

- **Backend**: Python, FastAPI, OpenAI Agents SDK. The live agent trace is streamed to the UI
  over Server-Sent Events.
- **Retrieval**: OpenAI file search over a vector store of synthetic policies.
- **Frontend**: a custom single-page UI (HTML/CSS/JS, no build step).

## Project structure

```
agents_pipeline.py     the agents, models, scoring and finalize/Q&A logic
server.py              FastAPI app (process, events/SSE, finalize, ask, outreach)
evidence.py           multimodal ingestion (audio, image, PDF, text)
setup_vectorstore.py  uploads the synthetic policies to a vector store
web/                  index.html · style.css · app.js
synthetic_data/       emails/ (4 sample claims), policies/, evidence/ (a scanned form)
app.py                optional lightweight Streamlit UI
```

## Getting started

You need an **OpenAI API key** (platform.openai.com — pay-as-you-go, not ChatGPT Plus). A demo
run costs a few cents.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set OPENAI_API_KEY
python setup_vectorstore.py   # uploads policies, saves VECTOR_STORE_ID to .env
python server.py
```

Open http://127.0.0.1:8000.

## Using it

1. On the home screen, pick one of the four sample claims (or upload a `.txt`/`.pdf`, or upload
   the scanned form in `synthetic_data/evidence/` to see the vision path).
2. Press **Process claim** and watch the agent trace run live.
3. Review the claim file: extracted data, coverage with the cited clause, triage decision and
   the audit trail.
4. **Approve / Reject** (a downstream action and customer message are generated), or **reopen**,
   **override the route**, **re-evaluate** with extra information, or **ask** a question about the
   claim. Everything is recorded in the audit trail and the JSON export.

## Bring your own API key

No key in your `.env`? Click **Add API key** in the top bar and paste your own OpenAI key. It is
stored only in your browser (localStorage) and sent to your local server with each request; the
server falls back to its `.env` key if none is set. Never commit your key to the repo.

## Notes

All sample data is **100% synthetic**. ClaimPilot is a decision aid that keeps a human in the
loop; it does not auto-settle or auto-reject claims, and it is not insurance advice.
