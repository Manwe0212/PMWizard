"use client";

import { FormEvent, useEffect, useState } from "react";

export function InvitationAcceptance() {
  const [token, setToken] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const value = params.get("token");
    // The fragment is never sent to the web server; remove it from the
    // address bar/history as soon as the client has read it into memory.
    window.history.replaceState(null, "", window.location.pathname);
    setToken(value && /^[A-Za-z0-9_-]{40,128}$/.test(value) ? value : "");
  }, []);

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || busy) return;
    setError(null);
    if (password !== confirmation) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/invitations/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ token, display_name: name.trim(), password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string" ? payload.detail : "Unable to accept invitation.",
        );
      }
      setPassword("");
      setConfirmation("");
      setToken(null);
      window.location.replace("/");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to accept invitation.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="authPage">
      <section className="loginCard">
        <div className="loginIntro">
          <div className="authBrandMark">P</div>
          <div>
            <div className="eyebrow">Secure invitation</div>
            <h1>Join a PMWizard project</h1>
            <p>Set your name and password to activate your invited account and project membership.</p>
          </div>
        </div>
        {token === null ? (
          <p>Checking invitation link…</p>
        ) : !token ? (
          <div className="loginError" role="alert">
            This invitation link is invalid or missing. Ask the project manager for a new link.
          </div>
        ) : (
          <form className="loginForm" onSubmit={accept}>
            <label>
              Display name
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="name"
                minLength={2}
                maxLength={120}
                required
              />
            </label>
            <label>
              New password (12+ characters)
              <input
                type="password"
                autoComplete="new-password"
                value={password}
                minLength={12}
                maxLength={256}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <label>
              Confirm password
              <input
                type="password"
                autoComplete="new-password"
                value={confirmation}
                minLength={12}
                maxLength={256}
                onChange={(event) => setConfirmation(event.target.value)}
                required
              />
            </label>
            {error && <div className="loginError" role="alert">{error}</div>}
            <button className="primaryButton full" type="submit" disabled={busy || name.trim().length < 2 || password.length < 12}>
              {busy ? "Activating…" : "Accept invitation & sign in"}
            </button>
          </form>
        )}
        <div className="loginSecurity">
          Invitation links expire after seven days and can be used once.
          Only the intended invited email is registered. Ask your project
          manager to revoke or reissue a lost link.
        </div>
      </section>
    </main>
  );
}
