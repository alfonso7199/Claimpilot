"""
ClaimPilot - multi-agent pipeline for insurance FNOL (First Notice of Loss).

Built with the OpenAI Agents SDK (`openai-agents` package).
Flow: Intake -> Policy (file search over policies) -> Triage,
orchestrated deterministically so the demo is reliable and so we can
show live what each agent is doing (the "agent trace").

100% synthetic data. Do not use with real information.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from agents import Agent, FileSearchTool, Runner

load_dotenv()

MODEL = os.getenv("CLAIMPILOT_MODEL", "gpt-4o")
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID", "")
CONFIDENCE_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# Structured output models
# ---------------------------------------------------------------------------


class Party(BaseModel):
    name: str = Field(description="Name of the person or entity involved")
    role: str = Field(description="Role: insured, third party, witness, etc.")


class ClaimIntake(BaseModel):
    """Data extracted from the claim email/form/call."""

    policy_number: Optional[str] = Field(
        default=None, description="Policy number if present"
    )
    claimant_name: Optional[str] = None
    claimant_email: Optional[str] = Field(
        default=None,
        description="Customer email address if present (e.g. the From: header)",
    )
    incident_date: Optional[str] = Field(
        default=None, description="Incident date (YYYY-MM-DD if possible)"
    )
    incident_type: Optional[str] = Field(
        default=None, description="auto, home, health, etc."
    )
    description: str = Field(description="Summary of what happened")
    location: Optional[str] = None
    damages: list[str] = Field(
        default_factory=list, description="List of reported damages/losses"
    )
    parties: list[Party] = Field(default_factory=list)
    estimated_amount_eur: Optional[float] = Field(
        default=None, description="Estimated damage amount in euros, if mentioned"
    )
    fraud_indicators: list[str] = Field(
        default_factory=list,
        description="Signs of potential fraud detected in the text",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Essential fields missing to process the claim (e.g. policy number)",
    )


class ClauseCitation(BaseModel):
    clause: str = Field(description="Clause identifier, e.g. 'Art. 4.2'")
    quote: str = Field(description="Verbatim text of the cited clause")


class CoverageAssessment(BaseModel):
    """Coverage verdict based on the policies (via file search)."""

    covered: bool
    clause_citations: list[ClauseCitation] = Field(default_factory=list)
    limit_eur: Optional[float] = Field(
        default=None, description="Applicable indemnity limit"
    )
    deductible_eur: Optional[float] = Field(
        default=None, description="Applicable deductible"
    )
    exclusions_triggered: list[str] = Field(default_factory=list)
    reasoning: str = Field(description="Why it is or is not covered")
    caveats: list[str] = Field(
        default_factory=list,
        description="Why this assessment is provisional, or what data is still "
        "needed to confirm coverage (e.g. policy number missing)",
    )


class TriageDecision(BaseModel):
    """Claim routing decision."""

    route: str = Field(
        description="straight_through | adjuster | investigation | pending_information"
    )
    rationale: str = Field(description="Justification for the chosen route")
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_payout_eur: Optional[float] = None
    accept_reasons: list[str] = Field(
        default_factory=list,
        description="Concrete reasons that support approving the claim",
    )
    decline_reasons: list[str] = Field(
        default_factory=list,
        description="Concrete reasons / red flags that support declining or holding",
    )
    fraud_flags: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------


def build_intake_agent() -> Agent:
    return Agent(
        name="IntakeAgent",
        model=MODEL,
        instructions=(
            "You are a claim intake agent (FNOL) for an insurance company. "
            "You receive a claim dossier that may combine several pieces of "
            "evidence (email or form text, a call transcript, image/photo "
            "analysis, scanned documents), each under an '=== EVIDENCE: ... ===' "
            "header. Reconcile them into a single, coherent claim. If two sources "
            "conflict, prefer explicit document/form data and note the conflict in "
            "the description. "
            "Extract the data into the structured schema. "
            "Capture the customer's email address (e.g. the From: header) in "
            "'claimant_email' when present. "
            "If any ESSENTIAL field needed to process the claim is missing "
            "(policy number, incident date or description), add it to "
            "'missing_fields'. "
            "If you detect signs of potential fraud (date inconsistencies, "
            "unusual rush to get paid, lack of witnesses in a large claim, "
            "damages that don't match the account), note them in "
            "'fraud_indicators'. "
            "Do not invent data that does not appear in the text."
        ),
        output_type=ClaimIntake,
    )


def build_policy_agent() -> Agent:
    tools = []
    if VECTOR_STORE_ID:
        tools.append(
            FileSearchTool(
                vector_store_ids=[VECTOR_STORE_ID],
                max_num_results=4,
            )
        )
    return Agent(
        name="PolicyAgent",
        model=MODEL,
        instructions=(
            "You are an expert agent on policy terms and conditions. "
            "Use the file search tool to locate in the policies the clauses "
            "relevant to the described claim. "
            "Determine whether the incident is covered and QUOTE VERBATIM the "
            "clause (number + text) that backs your verdict in 'clause_citations'. "
            "State the applicable limit, deductible and exclusions if any. "
            "If you find no support in the policies, set covered=false and explain it. "
            "Even if key data is missing (e.g. the policy number is absent or the "
            "exact policy cannot be matched), still give a best-effort PROVISIONAL "
            "assessment based on the incident type and typical policy terms, and list "
            "in 'caveats' what is missing or uncertain and what is needed to confirm. "
            "Do not refuse to assess. "
            "Never invent a clause that does not exist in the documents."
        ),
        output_type=CoverageAssessment,
        tools=tools,
    )


def build_triage_agent() -> Agent:
    return Agent(
        name="TriageAgent",
        model=MODEL,
        instructions=(
            "You are a claim triage agent. You receive the intake data and the "
            "coverage verdict. Decide the route:\n"
            "- 'straight_through': clear coverage, low amount (< 2000 EUR), no "
            "fraud signals -> direct payment.\n"
            "- 'adjuster': medium/high amount, complex damages or nuanced coverage "
            "-> assign to an adjuster.\n"
            "- 'investigation': there are fraud indicators or inconsistencies -> "
            "investigate.\n"
            "- 'pending_information': essential data is missing (e.g. no policy "
            "number, no incident date) so a final decision cannot be responsibly "
            "made yet -> hold for information.\n"
            "Always give a PROVISIONAL recommendation even with incomplete or "
            "suspicious data. Always populate BOTH 'accept_reasons' (why the claim "
            "could be approved) and 'decline_reasons' (red flags / why it could be "
            "denied or held), even if one list is short. "
            "Give a clear 'rationale' and a 'confidence' between 0 and 1, where "
            "confidence reflects how complete and consistent the information is. "
            "Copy any relevant fraud indicator to 'fraud_flags'. "
            f"If your confidence is lower than {CONFIDENCE_THRESHOLD} or the route is "
            "'pending_information', set requires_human_review=true."
        ),
        output_type=TriageDecision,
    )


# ---------------------------------------------------------------------------
# Orchestration + audit log
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    timestamp: str
    agent: str
    summary: str


@dataclass
class ClaimResult:
    intake: ClaimIntake
    coverage: Optional[CoverageAssessment]
    triage: Optional[TriageDecision]
    audit_log: list[AuditEntry] = field(default_factory=list)
    needs_more_info: bool = False
    info_request_email: Optional[str] = None


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def _draft_missing_info_email(intake: ClaimIntake) -> str:
    """When data is missing, draft an email requesting it (the trap case)."""
    drafter = Agent(
        name="InfoRequestAgent",
        model=MODEL,
        instructions=(
            "Draft a short, courteous and professional email in English addressed "
            "to the customer, asking ONLY for the data needed to process their "
            "claim. Do not ask for data you already have. "
            "Address the customer by name if known. "
            "Sign the email exactly as:\n"
            "ClaimPilot Claims Team\n"
            "Fictitious Insurer Inc.\n"
            "claims@fictitiousinsurer.com\n"
            "Do NOT leave any placeholder brackets like [Your Name]."
        ),
    )
    prompt = (
        "The following fields are missing: "
        + ", ".join(intake.missing_fields)
        + ".\nData already available: "
        + intake.model_dump_json()
    )
    res = await Runner.run(drafter, input=prompt)
    return str(res.final_output)


async def run_pipeline(
    claim_text: str,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> ClaimResult:
    """
    Run the full flow. `on_progress(agent, status)` is called at each step so the
    UI can show live which agent is working.
    """

    def notify(agent: str, status: str) -> None:
        if on_progress:
            on_progress(agent, status)

    audit: list[AuditEntry] = []

    # 1) INTAKE -----------------------------------------------------------
    notify("IntakeAgent", "Extracting claim data...")
    intake_agent = build_intake_agent()
    intake_res = await Runner.run(intake_agent, input=claim_text)
    intake: ClaimIntake = intake_res.final_output
    audit.append(
        AuditEntry(
            _now(),
            "IntakeAgent",
            f"Extracted {len(intake.damages)} damage item(s); "
            f"policy={intake.policy_number or 'N/A'}; "
            f"missing={intake.missing_fields or 'none'}",
        )
    )

    # Missing data -> AUTOMATED OUTREACH, but DO NOT stop. We still produce a
    # provisional claim file so the reviewer sees data, coverage, triage and gaps.
    info_email: Optional[str] = None
    if intake.missing_fields:
        notify("InfoRequestAgent", "Missing data detected: drafting outreach to obtain it...")
        info_email = await _draft_missing_info_email(intake)
        audit.append(
            AuditEntry(
                _now(),
                "InfoRequestAgent",
                f"Gaps: {', '.join(intake.missing_fields)}; outreach email drafted",
            )
        )

    # 2) POLICY -----------------------------------------------------------
    notify("PolicyAgent", "Checking coverage against the policies...")
    policy_agent = build_policy_agent()
    policy_input = (
        "Assess the coverage of this claim against the available policies.\n\n"
        + intake.model_dump_json(indent=2)
    )
    policy_res = await Runner.run(policy_agent, input=policy_input)
    coverage: CoverageAssessment = policy_res.final_output
    audit.append(
        AuditEntry(
            _now(),
            "PolicyAgent",
            f"covered={coverage.covered}; "
            f"{len(coverage.clause_citations)} clause(s) cited",
        )
    )

    # 3) TRIAGE -----------------------------------------------------------
    notify("TriageAgent", "Deciding the claim route...")
    triage_agent = build_triage_agent()
    triage_input = (
        "INTAKE:\n"
        + intake.model_dump_json(indent=2)
        + "\n\nCOVERAGE:\n"
        + coverage.model_dump_json(indent=2)
    )
    triage_res = await Runner.run(triage_agent, input=triage_input)
    triage: TriageDecision = triage_res.final_output

    # Confidence guardrail
    if triage.confidence < CONFIDENCE_THRESHOLD:
        triage.requires_human_review = True

    audit.append(
        AuditEntry(
            _now(),
            "TriageAgent",
            f"route={triage.route}; confidence={triage.confidence:.2f}; "
            f"human_review={triage.requires_human_review}",
        )
    )

    notify("Manager", "Claim file ready for human review.")
    return ClaimResult(
        intake=intake,
        coverage=coverage,
        triage=triage,
        audit_log=audit,
        needs_more_info=bool(intake.missing_fields),
        info_request_email=info_email,
    )


def run_pipeline_sync(
    claim_text: str,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> ClaimResult:
    """Synchronous wrapper for use from Streamlit."""
    return asyncio.run(run_pipeline(claim_text, on_progress=on_progress))


# ---------------------------------------------------------------------------
# Finalization (what happens after the human approves / rejects)
# ---------------------------------------------------------------------------


class Finalization(BaseModel):
    """The concrete downstream action triggered by the reviewer's decision."""

    decision: str = Field(description="approved | rejected")
    action: str = Field(
        description="machine label: payment_scheduled | assigned_adjuster | "
        "investigation_opened | claim_declined"
    )
    action_summary: str = Field(
        description="one-line description of the concrete action taken"
    )
    customer_message: str = Field(
        description="professional customer-facing email/letter in English"
    )
    next_steps: list[str] = Field(default_factory=list)


def build_action_agent() -> Agent:
    return Agent(
        name="ActionAgent",
        model=MODEL,
        instructions=(
            "You are the claims action agent. A human reviewer has just made a "
            "decision on a prepared claim file. Based on the decision AND the "
            "triage route, determine the concrete downstream action and draft the "
            "customer-facing communication in English. Rules:\n"
            "- decision 'approved' + route 'straight_through' -> action="
            "'payment_scheduled': schedule a direct payment to the bank account on "
            "file. If TRIAGE.estimated_payout_eur is present, use that exact amount "
            "as the payable amount because it is already net of deductible; do not "
            "subtract the deductible again. The message confirms approval, the "
            "amount and the expected timeline (e.g. 3-5 days).\n"
            "- decision 'approved' + route 'adjuster' -> action='assigned_adjuster': "
            "assign to a field adjuster; tell the customer an adjuster will contact "
            "them within 48 hours; do not confirm a final amount.\n"
            "- decision 'approved' + route 'investigation' -> action="
            "'investigation_opened': open an investigation case; acknowledge the "
            "claim, explain that additional review is required and may request "
            "documents; do NOT confirm any payment.\n"
            "- decision 'rejected' -> action='claim_declined': politely decline, give "
            "a clear reason grounded in the coverage assessment, and explain the "
            "appeals option.\n"
            "Keep the message concise and professional. Provide 2-4 concrete "
            "next_steps. "
            "Never use placeholder names, bracketed placeholders or generic company "
            "names. Sign every customer message exactly as:\n"
            "ClaimPilot Claims Team\n"
            "Fictitious Insurer Inc.\n"
            "claims@fictitiousinsurer.com\n"
            "Act on the route given in TRIAGE (it may have been overridden by the "
            "reviewer). If a REVIEWER NOTE is present, honor it and reflect it in "
            "the action and message."
        ),
        output_type=Finalization,
    )


async def finalize_claim(
    intake: dict,
    coverage: Optional[dict],
    triage: Optional[dict],
    decision: str,
    reviewer_note: str = "",
) -> Finalization:
    agent = build_action_agent()
    note_block = f"\n\nREVIEWER NOTE:\n{reviewer_note}" if reviewer_note.strip() else ""
    prompt = (
        f"REVIEWER DECISION: {decision}\n\n"
        f"INTAKE:\n{json.dumps(intake, ensure_ascii=False)}\n\n"
        f"COVERAGE:\n{json.dumps(coverage, ensure_ascii=False)}\n\n"
        f"TRIAGE:\n{json.dumps(triage, ensure_ascii=False)}"
        f"{note_block}"
    )
    res = await Runner.run(agent, input=prompt)
    return res.final_output


# ---------------------------------------------------------------------------
# Q&A over the assembled claim (reviewer can dig deeper)
# ---------------------------------------------------------------------------


def build_qa_agent() -> Agent:
    tools = []
    if VECTOR_STORE_ID:
        tools.append(
            FileSearchTool(vector_store_ids=[VECTOR_STORE_ID], max_num_results=4)
        )
    return Agent(
        name="QAAgent",
        model=MODEL,
        instructions=(
            "You answer questions from a claims reviewer about one specific claim. "
            "Ground your answer in the provided claim dossier and, when relevant, use "
            "the policy file search to check the terms. Quote the policy clause when "
            "you rely on it. If the answer cannot be determined from the available "
            "information, say so plainly and state what would be needed. Be concise "
            "and neutral; do not invent facts or clauses."
        ),
        tools=tools,
    )


async def answer_question(dossier: str, question: str) -> str:
    agent = build_qa_agent()
    res = await Runner.run(
        agent,
        input=f"CLAIM DOSSIER:\n{dossier}\n\nREVIEWER QUESTION:\n{question}",
    )
    return str(res.final_output)
