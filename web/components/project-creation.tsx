"use client";

import { FormEvent, useState } from "react";

export interface CreateProjectValues {
  name: string;
  description?: string;
  objective?: string;
  methodology?: "agile" | "waterfall" | "hybrid" | "other";
  start_date?: string;
  planned_end_date?: string;
}

export function ProjectCreation({
  onCreate,
  onCancel,
}: {
  onCreate: (values: CreateProjectValues) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [objective, setObjective] = useState("");
  const [methodology, setMethodology] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setError(null);
    if (startDate && endDate && endDate < startDate) {
      setError("Planned end must be on or after project start.");
      return;
    }
    setSubmitting(true);
    try {
      await onCreate({
        name: name.trim(),
        ...(description.trim() ? { description: description.trim() } : {}),
        ...(objective.trim() ? { objective: objective.trim() } : {}),
        ...(methodology ? { methodology: methodology as CreateProjectValues["methodology"] } : {}),
        ...(startDate ? { start_date: startDate } : {}),
        ...(endDate ? { planned_end_date: endDate } : {}),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create project.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="projectCreationOverlay" role="presentation">
      <section
        className="projectCreationPanel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="createProjectTitle"
      >
        <div className="eyebrow">Project onboarding</div>
        <h2 id="createProjectTitle">Create a project</h2>
        <p>
          Begin with the essentials. The project is private to your workspace,
          and you receive read and human-review access.
        </p>
        <form className="projectCreationForm" onSubmit={submit}>
          <label>
            Project name
            <input
              autoFocus
              required
              minLength={3}
              maxLength={120}
              value={name}
              placeholder="e.g. Customer onboarding rollout"
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Description (optional)
            <textarea
              maxLength={1000}
              rows={2}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <label>
            Objective (optional)
            <textarea
              maxLength={500}
              rows={2}
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
            />
          </label>
          <label>
            Methodology (optional)
            <select value={methodology} onChange={(event) => setMethodology(event.target.value)}>
              <option value="">Select later</option>
              <option value="agile">Agile</option>
              <option value="waterfall">Waterfall</option>
              <option value="hybrid">Hybrid</option>
              <option value="other">Other</option>
            </select>
          </label>
          <div className="projectCreationDates">
            <label>
              Start date (optional)
              <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </label>
            <label>
              Planned end (optional)
              <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            </label>
          </div>
          {error && <div className="loginError" role="alert">{error}</div>}
          <div className="projectCreationActions">
            <button type="button" className="secondaryButton" disabled={submitting} onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="primaryButton" disabled={submitting || name.trim().length < 3}>
              {submitting ? "Creating…" : "Create project"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
