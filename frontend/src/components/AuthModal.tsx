import { useState } from "react";
import { X, Mail, Lock, AlertCircle, User } from "lucide-react";
import { getAuth } from "../services/firebase";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AuthModal = ({ isOpen, onClose }: AuthModalProps) => {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const auth = getAuth();
      if (isRegister) {
        await auth.createUserWithEmailAndPassword(email, password, displayName);
      } else {
        await auth.signInWithEmailAndPassword(email, password);
      }
      onClose();
    } catch (err: any) {
      console.error("Auth error:", err);
      setError(err.message || "An authentication error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setError("");
    setLoading(true);
    try {
      const auth = getAuth();
      const firebase = (window as any).firebase;
      
      let provider: any;
      if (firebase && firebase.auth) {
        provider = new firebase.auth.GoogleAuthProvider();
      } else {
        provider = { providerId: "google.com" };
      }
      
      await auth.signInWithPopup(provider);
      onClose();
    } catch (err: any) {
      console.error("Google Auth error:", err);
      setError(err.message || "Google sign in failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6 bg-black/80 backdrop-blur-md transition-opacity duration-300 animate-fade-in">
      {/* Click-away overlay */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Modal Container */}
      <div className="relative w-full max-w-md bg-[#0d0d12]/90 border border-hairline rounded-2xl overflow-hidden shadow-2xl z-10 flex flex-col p-6">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-20 p-2 rounded-full bg-stage/60 hover:bg-stage/85 text-fg-muted hover:text-fg border border-hairline cursor-pointer transition-colors duration-150"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="mb-6 text-center">
          <h2 className="text-2xl font-bold text-fg">
            {isRegister ? "Create Account" : "Welcome Back"}
          </h2>
          <p className="text-xs text-fg-muted mt-2">
            {isRegister
              ? "Join the neon-drenched cinema grid"
              : "Sign in to upload and share high-vibe streams"}
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="flex items-center gap-3 p-3 mb-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <p className="line-clamp-2">{error}</p>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {isRegister && (
            <div className="flex flex-col gap-2">
              <label className="text-xs text-fg-muted font-bold uppercase tracking-wider">
                Display Name
              </label>
              <div className="relative">
                <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-muted" />
                <input
                  type="text"
                  required
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your Name / Channel"
                  className="w-full bg-[#161622]/65 hover:bg-[#1a1a29]/80 focus:bg-[#1a1a29] border border-hairline focus:border-red-500/40 rounded-xl py-3 pl-12 pr-4 text-sm text-fg outline-none transition-all duration-200"
                />
              </div>
            </div>
          )}

          <div className="flex flex-col gap-2">
            <label className="text-xs text-fg-muted font-bold uppercase tracking-wider">
              Email Address
            </label>
            <div className="relative">
              <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-muted" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-[#161622]/65 hover:bg-[#1a1a29]/80 focus:bg-[#1a1a29] border border-hairline focus:border-red-500/40 rounded-xl py-3 pl-12 pr-4 text-sm text-fg outline-none transition-all duration-200"
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-xs text-fg-muted font-bold uppercase tracking-wider">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-muted" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full bg-[#161622]/65 hover:bg-[#1a1a29]/80 focus:bg-[#1a1a29] border border-hairline focus:border-red-500/40 rounded-xl py-3 pl-12 pr-4 text-sm text-fg outline-none transition-all duration-200"
              />
            </div>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 disabled:opacity-50 text-white font-bold text-sm py-3.5 rounded-xl cursor-pointer shadow-lg shadow-red-500/10 hover:shadow-red-500/20 active:scale-[0.98] transition-all duration-150"
          >
            {loading ? "Authenticating..." : isRegister ? "Create Account" : "Sign In"}
          </button>
        </form>

        {/* Divider */}
        <div className="relative my-6 flex items-center justify-center">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-hairline"></div>
          </div>
          <span className="relative px-3 bg-[#0d0d12] text-[10px] text-fg-muted font-bold uppercase tracking-wider">
            or
          </span>
        </div>

        {/* Google Sign-In Button */}
        <button
          onClick={handleGoogleSignIn}
          disabled={loading}
          className="w-full flex items-center justify-center gap-3 py-3.5 bg-card hover:bg-card-hover border border-hairline rounded-xl text-fg hover:text-white font-bold text-sm transition-all duration-150 cursor-pointer disabled:opacity-50"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24">
            <path
              fill="currentColor"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="currentColor"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="currentColor"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
            />
            <path
              fill="currentColor"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            />
          </svg>
          <span>Continue with Google</span>
        </button>

        {/* Footer Toggle */}
        <div className="mt-6 text-center text-xs text-fg-muted">
          {isRegister ? (
            <p>
              Already have an account?{" "}
              <button
                onClick={() => {
                  setIsRegister(false);
                  setError("");
                }}
                className="text-red-400 hover:text-red-300 font-semibold cursor-pointer underline"
              >
                Sign In
              </button>
            </p>
          ) : (
            <p>
              Don't have an account yet?{" "}
              <button
                onClick={() => {
                  setIsRegister(true);
                  setError("");
                }}
                className="text-red-400 hover:text-red-300 font-semibold cursor-pointer underline"
              >
                Create Account
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
