"use client";

import { FormEvent, useEffect, useState } from "react";

export function PasswordResetRequestForm() {
  const [tenant, setTenant] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function request(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/password-reset/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ tenant_id: tenant.trim(), email: email.trim() }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof result.detail === "string"
          ? result.detail : "Unable to request password recovery.");
      }
      setSuccess(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to request recovery.");
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
            <div className="eyebrow">Account recovery</div>
            <h1>Reset your password</h1>
            <p>Request a one-use link for a verified PMWizard account.</p>
          </div>
        </div>
        {success ? (
          <div role="status" className="memberNotice">
            If this verified account exists, an email will be sent with
            instructions. The link expires in 30 minutes.
          </div>
        ) : (
          <form onSubmit={request} className="loginForm">
            <label>
              Workspace ID
              <input
                value={tenant}
                onChange={(event) => setTenant(event.target.value)}
                placeholder="Tenant UUID"
                autoComplete="organization"
                required
              />
            </label>
            <label>
              Account email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </label>
            {error && <div className="loginError" role="alert">{error}</div>}
            <button className="primaryButton full loginButton" type="submit" disabled={busy}>
              {busy ? "Requesting…" : "Send recovery email"}
            </button>
          </form>
        )}
        <p className="loginSecurity">
          Accounts without verified email must contact a trusted workspace
          operator for manual recovery. For security, PMWizard does not
          confirm whether an account exists.
        </p>
        <a href="/" className="authRecoveryLink">Back to sign in</a>
      </section>
    </main>
  );
}

export function PasswordResetConfirmForm() {
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const secret = params.get("token");
    // URL fragments are never sent to the initial page request; remove the
    // secret from the address bar/history immediately after reading.
    window.history.replaceState(null, "", window.location.pathname);
    setToken(secret && /^[A-Za-z0-9_-]{40,128}$/.test(secret) ? secret : "");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || busy) return;
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ token, password }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail : "Unable to reset your password.",
        );
      }
      setPassword("");
      setConfirm("");
      setToken(null);
      setDone(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reset password.");
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
            <div className="eyebrow">Account recovery</div>
            <h1>Choose a new password</h1>
            <p>Completing the reset will revoke all previous sessions.</p>
          </div>
        </div>
        {token === null ? (
          <p>Checking recovery link…</p>
        ) : done ? (
          <div className="memberNotice" role="status">
            Password changed. All previous sessions are invalidated.
            Sign in again with your new password.
          </div>
        ) : !token ? (
          <div className="loginError" role="alert">
            This recovery link is missing or invalid. Request a new link.
          </div>
        ) : (
          <form className="loginForm" onSubmit={submit}>
            <label>
              New password (12+ characters)
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <label>
              Confirm password
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                required
              />
            </label>
            {error && <div className="loginError" role="alert">{error}</div>}
            <button
              type="submit"
              className="primaryButton full loginButton"
              disabled={busy || password.length < 12 || password !== confirm}
            >
              {busy ? "Updating…" : "Reset password"}
            </button>
          </form>
        )}
        <a href="/" className="authRecoveryLink">Back to sign in</a>
      </section>
    </main>
  );
}
