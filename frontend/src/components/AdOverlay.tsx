import { useEffect, useRef, useState } from "react";
import { Megaphone } from "lucide-react";
import { Ad } from "../lib/api";

interface AdOverlayProps {
  ad: Ad;
  /** Called once the countdown finishes and the video should start. */
  onFinished: () => void;
}

const TICK_MS = 100;

/**
 * Pre-roll shown in the player frame before a video starts.
 *
 * Two treatments: an image ad fills the frame with the message beneath it, and
 * a text-only ad gets an animated typographic screen instead -- otherwise a
 * bare sentence on black for ten seconds reads like an error.
 *
 * The countdown is driven from a wall-clock deadline rather than by counting
 * ticks. A backgrounded tab throttles timers, and accumulating elapsed time
 * from intervals would make the ad outlast its duration by however long the
 * tab was hidden.
 */
export const AdOverlay = ({ ad, onFinished }: AdOverlayProps) => {
  const totalMs = Math.max(1, ad.durationSeconds) * 1000;
  const [remainingMs, setRemainingMs] = useState(totalMs);
  const [imageBroken, setImageBroken] = useState(false);
  const finishedRef = useRef(false);

  useEffect(() => {
    const deadline = Date.now() + totalMs;
    const finish = () => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      onFinished();
    };

    const timer = setInterval(() => {
      const left = deadline - Date.now();
      setRemainingMs(Math.max(0, left));
      if (left <= 0) {
        clearInterval(timer);
        finish();
      }
    }, TICK_MS);

    return () => clearInterval(timer);
    // Keyed on the ad so a different video restarts the countdown cleanly.
  }, [ad.id, totalMs, onFinished]);

  const secondsLeft = Math.ceil(remainingMs / 1000);
  const progress = 1 - remainingMs / totalMs;
  const showImage = ad.imageUrl && !imageBroken;

  return (
    <div className="absolute inset-0 z-20 flex flex-col bg-black overflow-hidden">
      {/* Label, so a viewer immediately understands why the video has not
          started rather than assuming it is broken. */}
      <div className="absolute top-3 left-3 z-30 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur-sm border border-white/15">
        <Megaphone className="w-3.5 h-3.5 text-amber-300" />
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/90">
          Ad
        </span>
      </div>

      <div className="absolute top-3 right-3 z-30 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur-sm border border-white/15">
        <span className="text-[11px] font-bold text-white/90 tabular-nums">
          Video in {secondsLeft}s
        </span>
      </div>

      {showImage ? (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 min-h-0 flex items-center justify-center p-4">
            <img
              src={ad.imageUrl as string}
              alt={ad.message}
              onError={() => setImageBroken(true)}
              className="max-w-full max-h-full object-contain ad-image-in"
            />
          </div>
          <p className="flex-shrink-0 px-6 pb-8 pt-2 text-center text-sm md:text-base font-medium text-white/90">
            {ad.message}
          </p>
        </div>
      ) : (
        // Text-only: the animated treatment. A drifting gradient field behind
        // the message, which itself scales in and holds.
        <div className="flex-1 relative flex items-center justify-center px-8 text-center">
          <div className="ad-aurora" aria-hidden="true" />
          <div className="relative z-10 max-w-2xl">
            <p className="ad-message font-display text-2xl md:text-4xl font-black leading-tight tracking-tight">
              {ad.message}
            </p>
          </div>
        </div>
      )}

      {/* Progress bar, mirroring the player's own scrubber position. */}
      <div className="absolute bottom-0 inset-x-0 h-1 bg-white/15">
        <div
          className="h-full bg-gradient-to-r from-vibe-red to-vibe-purple transition-[width] duration-100 ease-linear"
          style={{ width: `${Math.min(100, progress * 100)}%` }}
        />
      </div>
    </div>
  );
};
