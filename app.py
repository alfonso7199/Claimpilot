"""
ClaimPilot - demo UI (Streamlit).

3 views:
  1. New claim: upload an email / pick an example.
  2. Processing: live panel of which agent is working (agent trace).
  3. Claim file: extracted data, cited coverage, triage, approval and audit trail.

Run:  streamlit run app.py
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import streamlit as st

from agents_pipeline import ClaimResult, run_pipeline_sync

ROOT = Path(__file__).parent
EMAILS_DIR = ROOT / "synthetic_data" / "emails"

st.set_page_config(page_title="ClaimPilot", page_icon="🛡️", layout="wide")

ROUTE_LABELS = {
    "straight_through": ("✅ Direct payment (fast track)", "success"),
    "adjuster": ("👷 Assign to adjuster", "warning"),
    "investigation": ("🔍 Investigation (possible fraud)", "error"),
}


def load_example_emails() -> dict[str, str]:
    out: dict[str, str] = {}
    for f in sorted(glob.glob(str(EMAILS_DIR / "*.txt"))):
        out[Path(f).stem] = Path(f).read_text(encoding="utf-8")
    return out


def read_uploaded(uploaded) -> str:
    name = uploaded.name.lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(uploaded)
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            st.error("Could not read the PDF. Upload a .txt or paste the text.")
            return ""
    return uploaded.read().decode("utf-8", errors="ignore")


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
if "claim_text" not in st.session_state:
    st.session_state.claim_text = ""
if "decision" not in st.session_state:
    st.session_state.decision = None

# --------------------------------------------------------------------------
# Header + sidebar
# --------------------------------------------------------------------------
st.title("🛡️ ClaimPilot")
st.caption(
    "From FNOL to an auditable claim file in minutes · multi-agent flow with the "
    "OpenAI Agents SDK · 100% synthetic data"
)

with st.sidebar:
    st.header("Status")
    if os.getenv("OPENAI_API_KEY"):
        st.success("OPENAI_API_KEY detected")
    else:
        st.error("OPENAI_API_KEY missing (check .env)")
    if os.getenv("VECTOR_STORE_ID"):
        st.success("Policy vector store connected")
    else:
        st.warning("No VECTOR_STORE_ID: run setup_vectorstore.py")
    st.divider()
    st.markdown(
        "**Agents**\n\n"
        "1. IntakeAgent — extracts data\n"
        "2. PolicyAgent — checks coverage (file search)\n"
        "3. TriageAgent — decides the route\n\n"
        "Manager orchestrates + audit log."
    )
    if st.button("🔄 New claim", use_container_width=True):
        st.session_state.result = None
        st.session_state.claim_text = ""
        st.session_state.decision = None
        st.rerun()

# --------------------------------------------------------------------------
# VIEW 1 + 2: input and processing
# --------------------------------------------------------------------------
if st.session_state.result is None:
    st.subheader("1 · New claim")
    examples = load_example_emails()

    col1, col2 = st.columns(2)
    with col1:
        choice = st.selectbox(
            "Pick an example case",
            ["—"] + list(examples.keys()),
        )
        if choice != "—":
            st.session_state.claim_text = examples[choice]
    with col2:
        uploaded = st.file_uploader("...or upload an email (.txt / .pdf)", type=["txt", "pdf"])
        if uploaded is not None:
            st.session_state.claim_text = read_uploaded(uploaded)

    claim_text = st.text_area(
        "Claim text",
        value=st.session_state.claim_text,
        height=280,
        placeholder="Paste the claim email/notice here...",
    )

    if st.button("🚀 Process claim", type="primary", disabled=not claim_text.strip()):
        st.session_state.claim_text = claim_text
        st.subheader("2 · Processing (agents at work)")

        status_box = st.status("Starting pipeline...", expanded=True)

        def on_progress(agent: str, status: str) -> None:
            status_box.update(label=f"{agent}: {status}")
            status_box.write(f"**{agent}** — {status}")

        try:
            result: ClaimResult = run_pipeline_sync(claim_text, on_progress=on_progress)
            status_box.update(label="Pipeline complete ✅", state="complete")
            st.session_state.result = result
            st.rerun()
        except Exception as e:  # noqa: BLE001
            status_box.update(label="Pipeline error", state="error")
            st.exception(e)

# --------------------------------------------------------------------------
# VIEW 3: claim file
# --------------------------------------------------------------------------
else:
    result: ClaimResult = st.session_state.result
    intake = result.intake

    st.subheader("3 · Claim file")

    # Trap case: missing data
    if result.needs_more_info:
        st.warning(
            "⚠️ Essential data missing to process the claim: "
            + ", ".join(intake.missing_fields)
        )
        st.markdown("#### ✉️ Automated email requesting the missing information")
        st.info(result.info_request_email or "")
        with st.expander("Data extracted so far"):
            st.json(intake.model_dump())
        with st.expander("🧾 Audit trail"):
            for e in result.audit_log:
                st.text(f"[{e.timestamp}] {e.agent}: {e.summary}")
        st.stop()

    coverage = result.coverage
    triage = result.triage

    # Triage decision banner
    label, kind = ROUTE_LABELS.get(triage.route, (triage.route, "info"))
    getattr(st, kind)(f"**Triage decision:** {label}  ·  confidence {triage.confidence:.0%}")
    if triage.requires_human_review:
        st.warning("🧑‍⚖️ Guardrail triggered: requires human review before continuing.")

    tab_summary, tab_coverage, tab_triage, tab_audit = st.tabs(
        ["📋 Data", "📑 Coverage", "🧭 Triage", "🧾 Audit trail"]
    )

    with tab_summary:
        c1, c2 = st.columns(2)
        c1.metric("Policy", intake.policy_number or "N/A")
        c2.metric("Type", intake.incident_type or "N/A")
        c1.metric("Incident date", intake.incident_date or "N/A")
        c2.metric(
            "Estimated amount",
            f"€{intake.estimated_amount_eur:,.0f}" if intake.estimated_amount_eur else "N/A",
        )
        st.markdown(f"**Description:** {intake.description}")
        if intake.damages:
            st.markdown("**Damages:** " + ", ".join(intake.damages))
        if intake.parties:
            st.markdown("**Parties:** " + ", ".join(f"{p.name} ({p.role})" for p in intake.parties))
        if intake.fraud_indicators:
            st.error("**Fraud indicators:** " + ", ".join(intake.fraud_indicators))

    with tab_coverage:
        if coverage.covered:
            st.success("Claim COVERED")
        else:
            st.error("Claim NOT covered")
        cc1, cc2 = st.columns(2)
        cc1.metric("Limit", f"€{coverage.limit_eur:,.0f}" if coverage.limit_eur else "N/A")
        cc2.metric("Deductible", f"€{coverage.deductible_eur:,.0f}" if coverage.deductible_eur else "N/A")
        st.markdown(f"**Reasoning:** {coverage.reasoning}")
        if coverage.exclusions_triggered:
            st.warning("**Exclusions:** " + ", ".join(coverage.exclusions_triggered))
        st.markdown("**Cited clauses (traceability):**")
        if coverage.clause_citations:
            for cit in coverage.clause_citations:
                st.markdown(f"> **{cit.clause}** — {cit.quote}")
        else:
            st.caption("No citations (is the vector store configured?).")

    with tab_triage:
        st.markdown(f"**Route:** {label}")
        st.markdown(f"**Rationale:** {triage.rationale}")
        st.metric(
            "Estimated payout",
            f"€{triage.estimated_payout_eur:,.0f}" if triage.estimated_payout_eur else "N/A",
        )
        if triage.fraud_flags:
            st.error("**Fraud flags:** " + ", ".join(triage.fraud_flags))

    with tab_audit:
        for e in result.audit_log:
            st.text(f"[{e.timestamp}] {e.agent}: {e.summary}")
        st.download_button(
            "⬇️ Download claim file (JSON)",
            data=__import__("json").dumps(
                {
                    "intake": intake.model_dump(),
                    "coverage": coverage.model_dump(),
                    "triage": triage.model_dump(),
                    "audit_log": [e.__dict__ for e in result.audit_log],
                },
                ensure_ascii=False,
                indent=2,
            ),
            file_name="claimpilot_claim_file.json",
            mime="application/json",
        )

    # Human-in-the-loop
    st.divider()
    st.markdown("### 🧑‍⚖️ Human review")
    if st.session_state.decision:
        st.success(f"Claim file **{st.session_state.decision}** by the reviewer.")
    else:
        a, b = st.columns(2)
        if a.button("✅ Approve", type="primary", use_container_width=True):
            st.session_state.decision = "APPROVED"
            st.rerun()
        if b.button("❌ Reject", use_container_width=True):
            st.session_state.decision = "REJECTED"
            st.rerun()
