import { LogIn, ShieldAlert, ShieldX, Loader2 } from "lucide-react";
import { Logo } from "./Logo";

/**
 * The gate in front of the admin console.
 *
 * Renders three refusals that are deliberately kept distinct, because the
 * operator's next action differs in each case: not signed in (sign in), signed
 * in but not allowlisted (use a different account, or ask an existing admin),
 * and sign-in not configured on the server (a deployment problem, not
 * something the operator can fix from the browser).
 */
type SignInState = "loading" | "signedOut" | "denied" | "unconfigured";

interface AdminSignInProps {
  state: SignInState;
  theme: "dark" | "light";
  /** The address that was refused, shown so a wrong-account sign-in is obvious. */
  deniedEmail?: string | null;
  message?: string | null;
  busy?: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
}

export const AdminSignIn = ({
  state,
  theme,
  deniedEmail,
  message,
  busy,
  onSignIn,
  onSignOut,
}: AdminSignInProps) => (
  <div className="min-h-screen bg-stage text-fg flex flex-col items-center justify-center px-4">
    <div className="w-full max-w-sm text-center">
      <Logo theme={theme} className="w-[200px] mx-auto mb-2" shine={false} />
      <p className="text-[10px] uppercase tracking-[0.3em] text-fg-muted/70 font-bold mb-8">
        Admin console
      </p>

      {state === "loading" && (
        <div className="flex items-center justify-center gap-2 text-sm text-fg-muted py-6">
          <Loader2 className="w-4 h-4 animate-spin" />
          Checking your access…
        </div>
      )}

      {state === "signedOut" && (
        <>
          <p className="text-sm text-fg-muted mb-6">
            Sign in with an authorised Google account to manage events, videos
            and ads.
          </p>
          <button
            onClick={onSignIn}
            disabled={busy}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-gradient-to-r from-vibe-red via-vibe-purple to-vibe-red bg-[length:200%_100%] hover:bg-[position:100%_0] text-white font-bold shadow-lg shadow-vibe-purple/25 hover:shadow-xl hover:shadow-vibe-purple/40 transition-all duration-300 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <LogIn className="w-4 h-4" />
            )}
            Continue with Google
          </button>
        </>
      )}

      {state === "denied" && (
        <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/40 text-left">
          <div className="flex items-start gap-3">
            <ShieldX className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-bold text-fg">Not an admin</p>
              <p className="text-xs text-fg-muted mt-1 break-words">
                {deniedEmail ? (
                  <>
                    <span className="font-mono">{deniedEmail}</span> is not on
                    the allowlist. Ask an existing admin to add it, or sign in
                    with a different account.
                  </>
                ) : (
                  message || "That account is not on the admin allowlist."
                )}
              </p>
            </div>
          </div>
          <button
            onClick={onSignOut}
            className="w-full mt-4 py-2 rounded-xl bg-card border border-hairline text-xs font-bold text-fg-muted hover:text-fg transition-colors cursor-pointer"
          >
            Use a different account
          </button>
        </div>
      )}

      {state === "unconfigured" && (
        <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/40 text-left">
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-bold text-fg">Sign-in unavailable</p>
              <p className="text-xs text-fg-muted mt-1">
                {message ||
                  "Google sign-in is not configured on this server, so the admin console is disabled."}
              </p>
            </div>
          </div>
        </div>
      )}

      {message && state === "signedOut" && (
        <p className="text-xs text-red-500 mt-4">{message}</p>
      )}
    </div>
  </div>
);
