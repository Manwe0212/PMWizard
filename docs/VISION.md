# PMWizard Vision

## The intelligence layer for Project & Program Management

PMWizard is an open-source initiative exploring how artificial intelligence can understand the full context of projects and programs—not only tasks and schedules, but also risks, decisions, dependencies, resources, finances, stakeholders, meetings, documents, and outcomes.

The long-term goal is to create an AI-powered Project & Program Intelligence platform that can connect fragmented project information, reason across it, detect emerging risks, explain project health, and support better human decisions.

PMWizard is not intended to replace project managers. It is intended to give them a stronger, continuously updated understanding of what is happening across their projects and programs.

---

## 1. The Problem

Modern project information is fragmented across many tools:

- Jira, GitHub, Monday, Asana, Smartsheet and similar execution tools
- Slack, Teams and email conversations
- Meeting transcripts and minutes
- RAID logs
- Roadmaps and schedules
- Financial trackers and forecasts
- Resource and capacity plans
- Project documents and deliverables
- Decisions that often remain buried in conversations

Each system contains only part of the truth.

Project managers spend significant time collecting information, reconciling inconsistencies, preparing status reports, identifying dependencies, following up on actions, and determining whether a project is actually healthy.

Traditional dashboards show what has already been recorded. They rarely understand context or explain why something is happening.

PMWizard asks a different question:

> Can AI build and continuously reason over a connected representation of a project so that project managers can detect problems earlier and make better decisions?

---

## 2. Product Vision

PMWizard should evolve into a connected intelligence layer sitting above existing project systems.

```text
Jira / GitHub / Monday / Asana
Slack / Teams / Email
Documents / Meeting Notes
RAID / Finance / Resource Plans
              |
              v
        PMWizard Context Layer
              |
      Structured Project Model
              |
    AI + ML + Knowledge Graph
              |
              v
 Risks | Forecasts | Decisions
 Dependencies | Health | Insights
 Recommendations | Executive Views
```

Rather than requiring organizations to immediately abandon their existing tools, PMWizard should first learn to connect and understand them.

---

## 3. Core Principle: Project Context Before AI

PMWizard should not begin with the question:

> What can we do with an LLM?

It should begin with:

> What information does a project manager need in order to understand and manage a project effectively?

The AI layer should therefore be built on top of a meaningful project data model.

Core entities may include:

- Project
- Program
- Portfolio
- Workstream
- Phase
- Milestone
- Task
- Story
- Sprint
- Deliverable
- Resource
- Stakeholder
- Vendor
- Risk
- Assumption
- Issue
- Dependency
- Decision
- Action Item
- Change Request
- Budget
- Forecast
- Meeting
- Document
- Outcome

The relationships between these entities are as important as the entities themselves.

---

## 4. The Project Digital Twin

A long-term concept for PMWizard is a **Project Digital Twin**: a living digital representation of the current state of a project.

The digital twin may contain:

- Schedule state
- Financial state
- Resource capacity
- Risks and issues
- Dependencies
- Decisions
- Changes
- Deliverables
- Stakeholder activity
- Communication signals
- Historical performance

This would allow PMWizard to answer questions such as:

- What changed this week?
- What is the biggest threat to delivery?
- Which milestone is most likely to slip?
- Which dependency is becoming critical?
- Which risk has no mitigation?
- What decisions are blocking progress?
- Why did project health move from green to yellow?
- What happens if a vendor is delayed by two weeks?
- Which projects are competing for the same constrained resource?

---

## 5. From Project Intelligence to Program Intelligence

PMWizard should eventually reason not only within individual projects, but across programs and portfolios.

Examples:

- Detecting resource conflicts across projects
- Identifying shared vendor risks
- Mapping cross-project dependencies
- Comparing delivery patterns
- Finding systemic risks across a portfolio
- Forecasting program-level schedule or budget pressure
- Identifying which project requires leadership attention first

A program is more than a collection of project dashboards. PMWizard should understand how projects affect one another.

---

## 6. AI Architecture Direction

PMWizard should combine multiple AI approaches rather than relying on one model.

### Structured analytics
Use deterministic calculations for metrics such as schedule variance, budget variance, resource utilization, aging risks, unresolved dependencies, and milestone performance.

### Machine Learning
Use historical project data to estimate outcomes such as:

- Probability of project success
- Schedule delay risk
- Budget overrun risk
- Delivery health
- Customer or stakeholder satisfaction risk

### Retrieval-Augmented Generation (RAG)
Allow the system to retrieve relevant project documentation, meeting notes, decisions, and other unstructured information when answering questions.

### Knowledge Graphs
Represent relationships between projects, milestones, risks, decisions, resources, stakeholders, systems, and vendors.

### AI Agents
Over time, specialized agents could monitor domains such as:

- Risk
- Schedule
- Finance
- Resources
- Dependencies
- Project governance

A coordinating intelligence layer could combine those findings into recommendations for the project or program manager.

---

## 7. Open Project Context

A future objective is to define a vendor-neutral project representation that allows information from different tools to be normalized into a common structure.

Example:

```json
{
  "project": {
    "name": "Example Transformation Program",
    "status": "yellow"
  },
  "milestones": [],
  "risks": [],
  "issues": [],
  "dependencies": [],
  "decisions": [],
  "resources": [],
  "financials": {}
}
```

This could allow PMWizard to ingest information from Jira, GitHub, Monday, spreadsheets, documents, and other systems without making the intelligence layer dependent on a single vendor.

---

## 8. Initial Users

PMWizard is initially designed for people managing complex work, including:

- Project Managers
- Program Managers
- PMO teams
- Delivery Managers
- Product Operations teams
- Transformation leaders
- Engineering and technology leaders

Future versions may provide different experiences for executives, project contributors, finance teams, and portfolio leaders.

---

## 9. MVP Direction

The first PMWizard MVP should remain intentionally small.

### MVP Question

> Can we use structured project data to assess project health and identify delivery risk before a project fails?

### Initial scope

1. Define a reusable project data model.
2. Generate a synthetic dataset of projects.
3. Create baseline project-health rules and metrics.
4. Train an initial machine-learning model for delivery-risk prediction.
5. Expose explainable outputs showing the factors contributing to the prediction.
6. Build a simple interface or notebook to explore the results.

The MVP should prioritize learning, transparency, and reproducibility over feature volume.

---

## 10. Future Evolution

PMWizard may evolve through several stages:

### Phase 1 — Project Health AI
Structured project data, analytics, feature engineering, and predictive models.

### Phase 2 — PM Copilot
RAG over project documentation, meetings, RAID logs, and execution data.

### Phase 3 — Project Knowledge Graph
Connected reasoning across project entities and dependencies.

### Phase 4 — Project Intelligence Agents
Specialized agents for risk, schedule, finance, resources, and governance.

### Phase 5 — Program & Portfolio Intelligence
Cross-project reasoning, scenario analysis, shared-resource forecasting, and executive intelligence.

### Phase 6 — AI-Native Project Management Platform
A complete interface where planning, execution, communication, intelligence, and governance can coexist in one environment.

---

## 11. What PMWizard Is Not

At this stage, PMWizard is not:

- Another task-management clone
- A Jira replacement
- A chatbot attached to a project tracker
- An autonomous system that makes governance decisions without human oversight
- A system trained on confidential corporate information

The project should focus on intelligence, context, explainability, interoperability, and human decision support.

---

## 12. Open-Source and Data Principles

PMWizard should be developed publicly and responsibly.

Development examples and datasets should use:

- Synthetic data
- Publicly available data
- Explicitly authorized data
- Properly anonymized examples

No confidential client information, proprietary project documents, credentials, personal information, or internal company data should be committed to the repository.

AI-generated recommendations should be explainable whenever possible and remain subject to human judgment.

---

## 13. Success

PMWizard will be successful if it can progressively demonstrate that connected project information leads to better project intelligence.

Early success means being able to answer:

1. What is happening?
2. Why is it happening?
3. What is likely to happen next?
4. What requires attention?
5. What evidence supports that conclusion?

The long-term ambition is larger:

> Transform fragmented project data into connected intelligence that helps people deliver complex work more successfully.
