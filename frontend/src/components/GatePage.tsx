import { useEffect, useRef, useState } from "react";
import { ArrowRight, Ticket } from "lucide-react";
import { navigate, roomPath } from "../lib/router";
import { Ambience } from "./Ambience";
import { Logo } from "./Logo";
import { Footer } from "./Footer";

const LAST_CODE_KEY = "vibetube:lastEventCode";

export const rememberCode = (code: string) => {
  try {
    localStorage.setItem(LAST_CODE_KEY, code);
  } catch {
    // Private browsing modes reject writes; the gate still works without it.
  }
};

export const recallCode = (): string => {
  try {
    return localStorage.getItem(LAST_CODE_KEY) || "";
  } catch {
    return "";
  }
};

interface GatePageProps {
  theme: "dark" | "light";
}

// Must stay just under the .logo-launch duration so the room mounts while the
// mark is still blowing out, rather than after an empty beat.
const LAUNCH_MS = 420;

export const GatePage = ({ theme }: GatePageProps) => {
  const [code, setCode] = useState("");
  const [launching, setLaunching] = useState(false);
  const lastCode = recallCode();
  const launchTimer = useRef<number | undefined>(undefined);

  // Navigating away mid-launch would otherwise leave the timer to fire against
  // an unmounted component.
  useEffect(() => () => window.clearTimeout(launchTimer.current), []);

  const enter = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || launching) return;
    rememberCode(trimmed);

    const path = roomPath(trimmed);
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    if (reducedMotion) {
      navigate(path);
      return;
    }

    setLaunching(true);
    launchTimer.current = window.setTimeout(() => navigate(path), LAUNCH_MS);
  };

  return (
    <div className="min-h-screen stage-vignette relative bg-stage text-fg flex flex-col overflow-hidden">
      <Ambience beam />

      {/* flex-1 centres the gate in whatever space the footer leaves. */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-4 w-full max-w-md mx-auto text-center">
        {/* One animation per layer: the outer span owns the entrance/exit, the
            inner one the glow pulse, and the logo wrapper the idle drift.
            Stacking them on a single element would let only one `animation`
            declaration survive the cascade. */}
        <h1 className="mb-4">
          <span
            className={`block ${launching ? "logo-launch" : "rise"}`}
            style={launching ? undefined : { animationDelay: "60ms" }}
          >
            <span className="block holo-glow">
              <Logo
                theme={theme}
                className={`w-[300px] md:w-[360px] ${launching ? "" : "logo-float"}`}
              />
            </span>
          </span>
        </h1>

        <div
          className={`w-full flex flex-col items-center ${launching ? "gate-recede" : ""}`}
        >
          <p
            className="text-sm md:text-base text-fg-muted font-medium mb-2 rise"
            style={{ animationDelay: "140ms" }}
          >
            Enter your event code to step into the showroom.
          </p>

          <div
            className="flex items-center gap-3 mb-10 rise"
            style={{ animationDelay: "200ms" }}
          >
            <span className="h-px w-10 bg-gradient-to-r from-transparent to-vibe-red/50" />
            <span className="text-[10px] uppercase tracking-[0.35em] text-fg-muted/70 font-bold">
              Now Showing
            </span>
            <span className="h-px w-10 bg-gradient-to-l from-transparent to-vibe-purple/50" />
          </div>

          <form
          onSubmit={(e) => {
            e.preventDefault();
            enter(code);
          }}
          className="w-full flex flex-col gap-3"
        >
          <div
            className="relative code-field rise"
            style={{ animationDelay: "260ms" }}
          >
            <div className="code-field__halo" />
            <Ticket className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-fg-muted pointer-events-none z-10" />
            <input
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="EVENT CODE"
              aria-label="Event code"
              className="relative w-full bg-input border border-hairline rounded-2xl pl-12 pr-4 py-4 text-center text-lg font-display font-bold tracking-[0.3em] uppercase text-fg placeholder:text-fg-muted/50 placeholder:tracking-[0.2em] focus:outline-none focus:border-transparent transition-all duration-200"
            />
          </div>

          <button
            type="submit"
            disabled={!code.trim()}
            className="btn-shimmer rise w-full flex items-center justify-center gap-2 py-4 rounded-2xl bg-gradient-to-r from-vibe-red via-vibe-purple to-vibe-red bg-[length:200%_100%] hover:bg-[position:100%_0] text-white font-bold shadow-lg shadow-vibe-purple/25 hover:shadow-xl hover:shadow-vibe-purple/40 hover:scale-[1.015] active:scale-[0.99] transition-all duration-300 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:shadow-none"
            style={{ animationDelay: "320ms" }}
          >
            <span className="relative z-10">Enter Showroom</span>
            <ArrowRight className="relative z-10 w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" />
            </button>
          </form>

          {lastCode && (
            <button
              onClick={() => enter(lastCode)}
              className="mt-6 text-xs text-fg-muted hover:text-fg transition-colors cursor-pointer rise"
              style={{ animationDelay: "400ms" }}
            >
              Return to{" "}
              <span className="font-bold tracking-wider text-vibe-purple">{lastCode}</span>
            </button>
          )}
        </div>
      </div>

      <Footer />
    </div>
  );
};
