# ClaimPilot Publication Checklist

## Current Verdict

ClaimPilot is a strong first project for the hackathon. It matches HCL's Track 1
insurance FNOL use case, has a real multi-step agent flow, shows citations and an
audit trail, and includes human review instead of stopping at chatbot behavior.

## Validated Locally

- FastAPI app starts on `http://127.0.0.1:8000`.
- `/api/health` reports both `OPENAI_API_KEY` and `VECTOR_STORE_ID` configured.
- `/api/examples` returns the four synthetic demo cases.
- `01_auto_complete` runs end-to-end: intake, cited coverage, straight-through
  triage, confidence, estimated payout and audit log.
- `03_missing_policy_number` runs the trap case: information gaps detected,
  outreach email drafted, provisional coverage/triage created, human review
  forced.
- `04_suspected_fraud` runs the risk case: fraud indicators detected, theft
  exclusions cited, investigation route selected, human review forced.
- `/api/finalize` now keeps the payout amount stable and signs customer messages
  as ClaimPilot / Fictitious Insurer Inc.

## Must Do Before Submission

- Record a backup demo video under 3 minutes.
- Rehearse the live path at least 3 times: normal auto claim, missing-info claim,
  suspected-fraud claim.
- Review `ClaimPilot_pitch.pptx` and align the pitch to a 3-5 minute script.
- If publishing to GitHub, initialize a repo from `claimpilot/` and do not include
  `.env`, `.venv/`, `__pycache__/`, `.DS_Store`, or `outbox/`.
- If uploading a zip instead of GitHub, manually exclude `.env` and `.venv/`.
- Use only synthetic or non-sensitive evidence in the demo.
- Run `python scripts/demo_smoke.py` while the server is up before presenting.

## Recommended Demo Script

1. Open `http://127.0.0.1:8000` and choose `01_auto_complete`.
2. Show the agent trace moving through Evidence, Intake, Policy and Triage.
3. Point at the cited policy clauses and the audit trail.
4. Approve the claim and show the generated downstream customer message.
5. Reset and run `03_missing_policy_number` to show automated outreach.
6. If time remains, run `04_suspected_fraud` to show investigation routing.

## Nice Next Improvements

- Add one screenshot or short GIF to the README.
- Add a one-command zip/export script that excludes secrets and local artifacts.
- Polish the pitch with a single quantified impact claim: "hours to minutes,
  every decision cited and auditable."
