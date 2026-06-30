# ClaimPilot — Submission & video script

## Submission form answers (copy/paste)

**Agent workflow.** ClaimPilot turns any FNOL (First Notice of Loss) into an auditable claim
file. (1) An **evidence-intake step** normalizes whatever arrives — audio call (transcription),
photo/scanned form (vision), PDF or email — into one dossier. (2) **IntakeAgent** extracts the
structured claim (policy, dates, parties, damages, fraud signals, gaps). (3) **PolicyAgent**
uses OpenAI **file search over a vector store** of policies to decide coverage and quote the
exact clause. (4) **TriageAgent** routes the claim (direct payment / adjuster / investigation)
with confidence and reasons. (5) A **Manager** assembles the file and writes the audit log. A
human approves/rejects/reopens/overrides; approval fires an **Action agent** (payment / adjuster
/ investigation + customer message), and a **Q&A agent** answers questions over the file. A
guardrail forces human review when confidence < 0.7.

**OpenAI technology stack.** OpenAI **Agents SDK** (Agent + Runner) with **structured outputs**
(Pydantic `output_type`); the **Responses API** with the **file search tool** over an OpenAI
**vector store** for cited retrieval; **vision** (GPT-4o) for images/scans; **audio
transcription** (gpt-4o-transcribe / Whisper) for calls; live agent trace streamed over SSE.
Models: GPT-4o class. Built with **Codex**.

---

## Video script (target 4–5 min)

### Part 1 — Pitch deck (~90 seconds)

- **[Slide 1 — Title]** "Hi, I'm ⟨name⟩. This is **ClaimPilot** — from any claim, a call, a photo,
  a PDF or an email, to an auditable claim file in minutes. It's built with the OpenAI Agents SDK
  and Codex, for Track 1."
- **[Slide 2 — Problem]** "A claim arrives as free text, a call or a scan. A handler reads it,
  keys the data, finds the policy, checks coverage and decides where it goes — by hand. It takes
  26 to 48 hours to reach the right adjuster, it's inconsistent, and one missed clause is
  expensive."
- **[Slide 3 — How it works]** "Here's the **agent workflow**. Evidence intake normalizes audio,
  images, PDFs and text into one dossier. Then IntakeAgent extracts the facts, PolicyAgent checks
  coverage and **quotes the policy clause** using OpenAI file search, and TriageAgent decides the
  route. Six specialized agents, with a human in the loop and a confidence guardrail."
- **[Slide 4 — What the judges see]** "In the demo you'll see the agents run live, the cited
  clause, the trap case where the agent asks for missing data instead of inventing it, and the
  fraud case."
- **[Slide 5 — Impact & scale]** "Hours to minutes, every decision cited and auditable. The same
  pattern scales to prior auth in health, KYC in banking, disputes in logistics."

### Part 2 — Live demo (~3 minutes)

1. "Let me show it. I open ClaimPilot at **localhost:8000**."
2. "First, the key: I click **Add API key** in the top bar and paste my own OpenAI key — so
   anyone who clones the repo can run it with their own key. The dot turns green."
3. "I'll drop the **scanned claim form** from the samples — a photo of a paper FNOL. Watch the
   **agent trace** on the right: EvidenceIntake reads the image with vision, IntakeAgent extracts
   the data, PolicyAgent checks coverage, TriageAgent routes it."
4. "Here's the claim file. Notice the **coverage panel quotes the exact policy clause** — this is
   OpenAI file search over the policy vector store, so it's traceable, not a black box."
5. "Triage recommends a route with reasons to approve or decline. I'll click **Approve** — and the
   Action agent generates the downstream action and the customer email, all logged in the **audit
   trail**."
6. "Now the trap case: I pick the **incomplete email** with no policy number. The agent doesn't
   invent — it drafts an **outreach asking for what's missing**, and I can send it."
7. "And I can **ask a question** about the file, or **re-evaluate** with new info. That's
   ClaimPilot: from any evidence to an auditable, human-approved claim file."

> Tip: run `python setup_vectorstore.py` once before recording so the cited clauses work, and do a
> dry run so the live trace timing feels smooth.
