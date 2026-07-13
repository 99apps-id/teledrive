import { Cloud, RefreshCw } from "lucide-react";

export type AuthMode = "login" | "register";

type AuthScreenProps = {
  bootstrapping: boolean;
  authMode: AuthMode;
  onAuthModeChange: (mode: AuthMode) => void;
  email: string;
  onEmailChange: (value: string) => void;
  password: string;
  onPasswordChange: (value: string) => void;
  authError: string;
  isSubmitting: boolean;
  onSubmit: () => void;
};

export function AuthScreen({
  bootstrapping,
  authMode,
  onAuthModeChange,
  email,
  onEmailChange,
  password,
  onPasswordChange,
  authError,
  isSubmitting,
  onSubmit,
}: AuthScreenProps) {
  if (bootstrapping) {
    return (
      <main className="auth-shell">
        <div className="auth-panel auth-bootstrapping" aria-live="polite" role="status">
          <RefreshCw size={20} className="spinning" aria-hidden="true" />
          <p>Checking session…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="auth-shell">
      <form
        className="auth-panel"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div className="brand compact">
          <div className="brand-mark">
            <Cloud size={22} aria-hidden="true" />
          </div>
          <div>
            <strong>TeleDrive</strong>
            <span>Private file manager</span>
          </div>
        </div>
        <h1>{authMode === "register" ? "Create admin account" : "Sign in"}</h1>
        <label>
          Email
          <input
            name="email"
            type="email"
            value={email}
            onChange={(event) => onEmailChange(event.target.value)}
            autoComplete="email"
            spellCheck={false}
            placeholder="you@example.com"
            required
          />
        </label>
        <label>
          Password
          <input
            name="password"
            type="password"
            value={password}
            onChange={(event) => onPasswordChange(event.target.value)}
            autoComplete={authMode === "register" ? "new-password" : "current-password"}
            placeholder="Enter a strong password"
            required
            minLength={8}
          />
        </label>
        {authError ? (
          <p className="auth-error" role="alert">
            {authError}
          </p>
        ) : null}
        <button className="tool-button primary" type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? authMode === "register"
              ? "Creating account…"
              : "Signing in…"
            : authMode === "register"
              ? "Create account"
              : "Sign in"}
        </button>
        <button
          className="tool-button"
          type="button"
          onClick={() => onAuthModeChange(authMode === "register" ? "login" : "register")}
        >
          {authMode === "register" ? "I already have an account" : "Create account"}
        </button>
      </form>
    </main>
  );
}
