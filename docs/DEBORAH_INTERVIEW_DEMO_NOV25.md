# PMWizard — Interview Demonstration Readiness (November 25, 2026)

**Audience:** Deborah — technical/experience-focused Project Manager interview.
**Goal:** Present PMWizard as a working personally driven PM/PMO product prototype
that demonstrates structured project intelligence, governance, and delivery
management expertise. This is an **interview demonstration**, not a
commercial or public deployment. **Never claim that synthetic data is live
customer data, or that an unavailable connector/AI provider works.**

## One-line value proposition

> "PMWizard is a project intelligence layer designed to turn fragmented
> delivery information into evidence-backed actions, transparent health
> indicators, and executive updates — with the project manager retaining
> control of every consequential change."

## Prioritized readiness gate

| Priority | Workstream | Acceptance evidence | Stop condition |
|---|---|---|---|
| P0 | Local Docker demo | Login, project selection, health and inbox load twice without errors | Unable to authenticate or load |
| P0 | AI status report | Connect authorized OpenAI API securely and generate one grounded draft, with fact references and no unsupported claims | Report generator errors or hallucinates project state |
| P0 | Clean browser | Disable Dark Reader for localhost; confirm Next.js dev overlay has no active hydration errors | Red overlay or broken rendering persists |
| P0 | Demo case | Atlas Delivery shows a coherent story: health, RAID, one approved action, audit, factual draft | Screens disagree about project state |
| P0 | Demo contingency | Screenshots or a short local screen recording from the same synthetic dataset, saved privately | No offline fallback |
| P1 | Executive visual polish | Critical figures readable on a laptop; consistent widths, spacing and labels | Hard-to-read dashboard |
| P1 | Interview script | 5–7 minute demo practiced aloud in English within allotted time | Demo too long or unclear |
| P1 | Technical defense | Explain Python/FastAPI, PostgreSQL, Next.js, Docker, human-in-the-loop, permissions, OpenAI API, limitations | Unable to distinguish built vs proposed |
| P2 | Integrations | Show connector configuration surfaces only; actual source sync requires real sandbox credentials and tested permission model | Demo implies untested live Jira/Microsoft integration |
| P2 | Budget/Tempo | Present as **roadmap**, not shipped capability | Misrepresents financial integration status |
| P2 | Public hosting | Not needed for local live screen share; don't rush internet exposure | Exposing demo credentials publicly |

## Exact demo narrative — approx. 6 minutes

**0:00–0:45 | Context and problem.** Describe project delivery
information distributed across tools, meetings and email, and the need
for a single PM-controlled intelligence layer. Explain that PMWizard is
a prototype you have been designing and validating personally, using
realistic **synthetic** delivery scenarios.

**0:45–1:40 | Executive Dashboard.** Open Atlas Delivery. Demonstrate
current Health Score and critical RAID signals, and explain that the
executive view aggregates only authorized project data. Do **not**
memorize one Health Score: read the value live.

**1:40–2:35 | Project Health.** Open Explainable V0, show factor scores,
weights, coverage and history. Distinguish deterministic calculations
from LLM output. Sources score may be unavailable (not zero); do not
claim 100% coverage when it is 85%.

**2:35–3:40 | Governed decisions.** Show the accepted synthetic
"Unblock vendor integration review" proposal in Activity Timeline:
the human accepted the AI suggestion, and a governed Action Item
changed from "Blocked" to "Pending External". Show that the related
RAID dependency remained blocked, which is legitimate: accepting the
proposal does NOT imply vendor sign-off. Check the exact current status
in Project Memory during the demo.

**3:40–4:40 | Status Reports.** With an authorized OpenAI API provider
configured, generate a 7-day Executive/Sponsor draft. Show cited fact
IDs and data-quality caveats. Say explicitly that generated wording
requires human approval. **If the provider is not configured, skip this
live step and show a prior verified screenshot with an explicit
"previously recorded" label; never imply that a failed generation
succeeded.**

**4:40–5:20 | Governance and permissions.** Show Activity Timeline,
source traces and optional Members & Roles. Explain that permissions
are project-scoped and audited; the user must review changes before
the governed project state is updated.

**5:20–6:00 | Architecture and close.** State that Next.js is the web
UI, Python/FastAPI is the backend, PostgreSQL stores project truth,
and the OpenAI Responses API is an optional structured-generation
provider. Integrations, budget tracking and predictive intelligence
are areas of continued development, not finished products.

## Suggested English talk track (practice, do not read verbatim)

"Deborah, I wanted to share something I have been building alongside
my project delivery work. In complex programs, the hardest part is often
not scheduling tasks — it is reconciling what different teams and
systems are telling us and deciding what truly needs attention."

"PMWizard is my attempt to turn that fragmented information into
structured, explainable project intelligence. The executive dashboard
summarizes critical delivery signals, while the health engine explains
which risks, dependencies and overdue decisions contribute to the
overall score."

"The differentiator for me is governance. AI can propose an update and
show the evidence behind it, but it doesn't silently rewrite project
truth. A project manager reviews the proposal, and the final action
is captured in the audit trail."

"Here is a synthetic example of a vendor integration dependency.
After human review, an action shifted from Blocked to Pending
External, while the underlying dependency remained blocked. That
distinction matters because status updates should reflect what
has actually happened, not an optimistic interpretation."

"I am now adding structured status reporting on top of those governed
facts. The model drafts wording, but citations and human review
remain part of the workflow."

"Architecturally, this is a Next.js, Python/FastAPI and PostgreSQL
application running locally in Docker. My next focus is secure
integration with enterprise project data and validating the workflow
with actual project managers. This is an MVP prototype, not a
production SaaS — but it demonstrates the kind of delivery problem
I enjoy solving."

## Likely questions and defensible answers

**Did you code everything yourself?**
"I designed the product requirements and governance workflow, directed
AI-assisted implementation, and have been testing the system end to
end. I review the behavior and iterate through GitHub pull requests."
Be accurate about the contribution of AI coding assistants and tests.

**What problem does it solve beyond Jira?**
"It is intended to complement existing systems by reconciling
context, evidence and executive decision signals. Jira remains
a source of execution truth; PMWizard is a PM intelligence layer,
not a replacement for all workflow tools."

**How do you prevent hallucinations?**
"The report generator compiles canonical, permission-filtered facts.
Structured output statements must cite fact IDs; unsupported numbers
are rejected, and a human reviews the draft. This reduces, but does
not eliminate, errors in narrative interpretation."

**How do you manage confidential data?**
"Project-scoped permission checks, audited changes and token hashing
are in the prototype. Production deployment still requires a
security review, operational controls and customer-specific
requirements. Today the demo uses synthetic data."

**Does it read real Microsoft 365/Jira sources or track Tempo budgets?**
"The architecture anticipates connectors, and some source-management
foundations exist, but I will not claim end-to-end production
connectivity or live Tempo budget tracking before they are tested.
Those are planned extensions."

**How are you measuring success?**
"Initial metrics would include time spent collecting updates,
percentage of AI proposals accepted or edited, grounded citation
coverage, overdue decision resolution and project-health coverage.
We need a user pilot to estimate actual time savings."

**What would you do next as a PM?**
"Pilot on one controlled program, establish baseline metrics,
validate connector permissions, iterate from PM feedback,
and only then expand to portfolio-level intelligence."

## Operating checklist before the interview

1. Confirm Docker Desktop engine is running.
2. Open `http://localhost:3000/` in Chrome; use the synthetic demo
   account from `.env.demo`. Do not display that file on-screen.
3. Disable Dark Reader on localhost. The observed hydration error
   contained `data-darkreader-mode` and came from browser injection.
4. Open Atlas Delivery, verify Project Memory and Executive Dashboard
   describe the same governed state.
5. Validate actual OpenAI API access and key **privately**; enable
   the backend configuration without committing secrets. Set a small
   spending budget/alerts on the API platform and pre-generate a
   grounded report for backup.
6. Keep one browser tab for the demo. Turn off notifications, close
   unrelated tabs and hide personal names/inboxes.
7. Run the demo once uninterrupted, then rehearse it with timing.
8. Take screenshots of the key steps or save an offline copy for
   connectivity fallback. Mark screenshots as synthetic demo evidence.
9. Do not seed/reset or delete the Docker PostgreSQL volume just
   before the call: that can erase the synthetic acceptance history.
10. Prepare a short architecture diagram and a single-page feature
    maturity table: **working**, **pilot validation pending**,
    **roadmap**. Don't pitch future functionality as shipped.

## Wednesday go/no-go for the *interview demo* (not customer rollout)

**GO** only if login, executive dashboard, Project Health, Project
Memory and audit timeline can be demonstrated in a private local
session without severe UI errors, and all claims match the actual
running build. Report generation is included live only when a
configured OpenAI provider has passed a dry run, otherwise marked
as pending. Have an offline fallback and a clear limitations answer.

This document does not certify real-user UAT, production safety or
commercial launch.
