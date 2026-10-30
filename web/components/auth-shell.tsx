"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { InboxClient } from "@/components/inbox-client";
import { ProjectCreation, type CreateProjectValues } from "@/components/project-creation";
import type { ProjectAccess, WebSession } from "@/lib/types";

async function jsonRequest<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : `Request failed with status ${response.status}`;
    throw Object.assign(new Error(detail), { status: response.status });
  }
  return payload as T;
}

export function AuthShell() {
  const [session, setSession] = useState<WebSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [authenticating, setAuthenticating] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tenantId, setTenantId] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const loadSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await jsonRequest<WebSession>("/api/session");
      setSession(data);
    } catch (requestError) {
      const status =
        requestError &&
        typeof requestError === "object" &&
        "status" in requestError
          ? Number((requestError as { status: unknown }).status)
          : null;
      if (status === 401) {
        setSession(null);
      } else {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load PMWizard session.",
        );
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  async function login(event: FormEvent) {
    event.preventDefault();
    setAuthenticating(true);
    setError(null);
    try {
      await jsonRequest("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          email,
          password,
        }),
      });
      setPassword("");
      await loadSession();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to sign in.",
      );
    } finally {
      setAuthenticating(false);
    }
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    setSession(null);
    setPassword("");
    setError(null);
  }

  async function selectProject(projectId: string) {
    setSelecting(true);
    setError(null);
    try {
      await jsonRequest("/api/project-selection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      setSession((current) =>
        current
          ? { ...current, selected_project_id: projectId }
          : current,
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to select project.",
      );
    } finally {
      setSelecting(false);
    }
  }

  async function createProject(values: CreateProjectValues) {
    const created = await jsonRequest<ProjectAccess>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    await jsonRequest("/api/project-selection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: created.project_id }),
    });
    setShowCreateProject(false);
    await loadSession();
  }

  const selectedProject = useMemo(
    () =>
      session?.projects.find(
        (project) => project.project_id === session.selected_project_id,
      ) ?? null,
    [session],
  );

  if (loading) {
    return (
      <main className="authPage">
        <div className="authLoading">
          <div className="authBrandMark">P</div>
          <strong>Loading PMWizard</strong>
          <span>Restoring your secure session…</span>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="authPage">
        <section className="loginCard">
          <div className="loginIntro">
            <div className="authBrandMark">P</div>
            <div>
              <div className="eyebrow">Project Intelligence</div>
              <h1>Welcome to PMWizard</h1>
              <p>
                Sign in to review evidence-backed project updates and govern
                what becomes project truth.
              </p>
            </div>
          </div>

          <form onSubmit={login} className="loginForm">
            <label>
              Workspace ID
              <input
                value={tenantId}
                onChange={(event) => setTenantId(event.target.value)}
                placeholder="Tenant UUID"
                autoComplete="organization"
                required
              />
            </label>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••••••"
                autoComplete="current-password"
                required
              />
            </label>

            {error && <div className="loginError">{error}</div>}

            <button
              className="primaryButton full loginButton"
              type="submit"
              disabled={authenticating}
            >
              {authenticating ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="loginSecurity">
            <span>●</span>
            Passwords are hashed with Argon2id. Sessions use signed,
            short-lived tokens stored in HttpOnly cookies.
          </div>
        </section>
      </main>
    );
  }

  if (!selectedProject) {
    return (
      <main className="projectSelectPage">
        <header className="projectSelectHeader">
          <div className="brand">
            <div className="brandMark">P</div>
            <div>
              <strong>PMWizard</strong>
              <span>Project Intelligence</span>
            </div>
          </div>
          <div className="accountMenuStatic">
            <div>
              <strong>{session.user.display_name}</strong>
              <span>{session.user.email}</span>
            </div>
            <button type="button" onClick={() => void logout()}>
              Sign out
            </button>
          </div>
        </header>

        <section className="projectPicker">
          <div className="eyebrow">Authorized workspace</div>
          <h1>Select a project</h1>
          <p>
            PMWizard will only show projects assigned to your account. Permissions
            are resolved separately for each project.
          </p>

          {error && <div className="loginError">{error}</div>}

          <button
            className="primaryButton"
            type="button"
            onClick={() => setShowCreateProject(true)}
          >
            + New project
          </button>

          {session.projects.length === 0 ? (
            <div className="noProjects">
              <strong>No project memberships found</strong>
              <span>Create your first project here, or ask an administrator for access to an existing one.</span>
            </div>
          ) : (
            <div className="projectGrid">
              {session.projects.map((project) => (
                <ProjectCard
                  key={project.project_id}
                  project={project}
                  disabled={selecting}
                  onSelect={() => void selectProject(project.project_id)}
                />
              ))}
            </div>
          )}
        </section>
        {showCreateProject && (
          <ProjectCreation
            onCreate={createProject}
            onCancel={() => setShowCreateProject(false)}
          />
        )}
      </main>
    );
  }

  return (
    <>
    <InboxClient
      key={selectedProject.project_id}
      projectId={selectedProject.project_id}
      projectName={selectedProject.name}
      projects={session.projects}
      userName={session.user.display_name}
      userEmail={session.user.email}
      onProjectChange={selectProject}
      onLogout={logout}
      projectSwitching={selecting}
      onNewProject={() => setShowCreateProject(true)}
    />
    {showCreateProject && (
      <ProjectCreation
        onCreate={createProject}
        onCancel={() => setShowCreateProject(false)}
      />
    )}
    </>
  );
}

function ProjectCard({
  project,
  disabled,
  onSelect,
}: {
  project: ProjectAccess;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className="projectCard"
      type="button"
      onClick={onSelect}
      disabled={disabled}
    >
      <div className="projectCardIcon">◇</div>
      <div>
        <strong>{project.name}</strong>
        <span>{project.role.replaceAll("_", " ")}</span>
      </div>
      <div className="projectCardMeta">
        {project.status && <span>{project.status}</span>}
        <b>Open →</b>
      </div>
    </button>
  );
}
