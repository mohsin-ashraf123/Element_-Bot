import type { FormEvent } from "react";
import { useState } from "react";
import { Navigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { useAuth } from "../lib/auth";

export function Login() {
  const { user, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch {
      setError("Invalid username or password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card reveal">
        <div className="auth-brand">
          <div className="auth-logo">
            <Icon name="logo" />
          </div>
          <div>
            <h1>PairFlow</h1>
            <p>Automation Control Panel</p>
          </div>
        </div>

        <form className="auth-form" onSubmit={onSubmit}>
          <label className="inp-lbl" htmlFor="username">
            Username
          </label>
          <input
            id="username"
            className="inp"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="admin"
            required
          />

          <label className="inp-lbl" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            className="inp"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />

          {error && (
            <div className="auth-error" role="alert">
              <Icon name="warn" size={14} />
              {error}
            </div>
          )}

          <button className="btn primary auth-submit" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="auth-foot">
          Credentials are set in <code>ADMIN_USERNAME</code> / <code>ADMIN_PASSWORD</code>
        </p>
      </div>
    </div>
  );
}
