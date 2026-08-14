import { CSSProperties, useEffect, useRef, useState } from "react";
import { Link2, Check, Linkedin } from "lucide-react";

/**
 * Share targets for a single video.
 *
 * The link points at the showroom with the video preselected, so a recipient
 * lands on that video rather than the grid. Copy is offered alongside the
 * social targets because it is the one that works everywhere -- group chats,
 * email, and Slack included.
 */
interface ShareButtonsProps {
  url: string;
  title: string;
  /** Uploader's display name, used to write the post in their voice. */
  authorName?: string;
  /** Video id. Seeds the variant so it matches the server-rendered card. */
  seed?: string;
}

const ANONYMOUS_NAMES = new Set(["", "anonymous vibe", "anonymous"]);

// Kept byte-identical to CREDITED_BLURBS / ANONYMOUS_BLURBS in
// backend/main.py, including the pick() hash, so the X post and the LinkedIn
// card say the same thing about the same video.
const CREDITED_BLURBS = [
  `🍿 Grab the popcorn — {name} made "{title}" with Google Cloud and Gemini.`,
  `🎬 Lights, camera, {name}! "{title}", built with Google Cloud and Gemini.`,
  `🚀 {name} shipped it: "{title}", cooked up with Google Cloud and Gemini.`,
  `✨ Straight from {name}'s brain to your screen — "{title}", made with Google Cloud and Gemini.`,
  `🤖 {name} + Google Cloud + Gemini = "{title}". Roll the tape.`,
  `🎧 {name} hit record and out came "{title}", powered by Google Cloud and Gemini.`,
];

const ANONYMOUS_BLURBS = [
  `🍿 Grab the popcorn — "{title}", made with Google Cloud and Gemini.`,
  `🎬 Lights, camera, "{title}" — built with Google Cloud and Gemini.`,
  `🚀 Freshly shipped: "{title}", cooked up with Google Cloud and Gemini.`,
  `✨ Someone made "{title}" with Google Cloud and Gemini, and it is worth a look.`,
  `🤖 Google Cloud + Gemini = "{title}". Roll the tape.`,
  `🎧 Somebody hit record and out came "{title}", powered by Google Cloud and Gemini.`,
];

/**
 * Stable index from a seed. Must match pick_variant() in backend/main.py.
 *
 * Deterministic rather than random so the text never changes between the card
 * someone previews and the post they publish, while different videos still
 * get different lines -- 300 identical posts in one feed reads like spam.
 */
const pick = (seed: string, count: number): number => {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (Math.imul(h, 31) + seed.charCodeAt(i)) >>> 0;
  }
  return h % count;
};

/** The pre-filled post text for X. */
const buildShareText = (title: string, authorName?: string, seed?: string): string => {
  const name = (authorName ?? "").trim();
  const variants = ANONYMOUS_NAMES.has(name.toLowerCase())
    ? ANONYMOUS_BLURBS
    : CREDITED_BLURBS;
  const line = variants[pick(seed || title, variants.length)]
    .replace("{name}", name)
    .replace("{title}", title);
  return `${line}\n\nWatch it on Vibetube 👇`;
};

const COPIED_RESET_MS = 2000;

/** X's own mark; lucide still ships the pre-rebrand bird. */
const XIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
    <path d="M18.9 1.15h3.68l-8.04 9.19L24 22.85h-7.41l-5.8-7.58-6.64 7.58H.46l8.6-9.83L0 1.15h7.59l5.24 6.93zm-1.29 19.5h2.04L6.49 3.24H4.3z" />
  </svg>
);

export const ShareButtons = ({ url, title, authorName, seed }: ShareButtonsProps) => {
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(resetTimer.current), []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.clearTimeout(resetTimer.current);
      resetTimer.current = window.setTimeout(() => setCopied(false), COPIED_RESET_MS);
    } catch {
      // Clipboard access needs a secure context and can be denied outright.
      // Selecting the URL by hand still works, so fail quietly.
    }
  };

  const shareText = buildShareText(title, authorName, seed);
  const targets = [
    {
      label: "Share on X",
      href: `https://x.com/intent/post?url=${encodeURIComponent(url)}&text=${encodeURIComponent(shareText)}`,
      icon: <XIcon className="w-3.5 h-3.5" />,
      name: "X",
      // X's mark is monochrome, so the chip has to invert against its
      // surroundings. Fixed light rather than theme-driven: the player modal
      // is dark in both themes, and keying this to the page theme rendered a
      // near-black chip on a near-black panel.
      style: { background: "#f5f3f0", color: "#0b0b0f" } as CSSProperties,
    },
    {
      // LinkedIn dropped support for title/summary parameters; it reads the
      // page's own metadata, so only the URL is worth sending.
      label: "Share on LinkedIn",
      href: `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`,
      icon: <Linkedin className="w-4 h-4" />,
      name: "LinkedIn",
      style: { background: "#0A66C2", color: "#ffffff" } as CSSProperties,
    },
  ];

  // Solid, brand-coloured fills rather than muted outlines: these were easy to
  // miss when they read as another line of grey text next to the timestamp.
  const buttonBase =
    "flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold " +
    "shadow-sm hover:shadow-md hover:scale-[1.04] active:scale-[0.98] " +
    "transition-all duration-200 cursor-pointer whitespace-nowrap";

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      <span className="text-[10px] uppercase font-bold tracking-[0.2em] text-fg-muted mr-0.5">
        Share
      </span>

      {targets.map((target) => (
        <a
          key={target.name}
          href={target.href}
          target="_blank"
          // noreferrer too: opener access is the actual risk, and noopener
          // alone still leaks the referrer.
          rel="noopener noreferrer"
          aria-label={target.label}
          className={buttonBase}
          style={target.style}
        >
          {target.icon}
          <span>{target.name}</span>
        </a>
      ))}

      <button
        type="button"
        onClick={copy}
        aria-label="Copy link to this video"
        className={`${buttonBase} border ${
          copied
            ? "bg-emerald-500/15 border-emerald-400/50 text-emerald-300"
            : "bg-card border-hairline text-fg hover:border-vibe-purple/50"
        }`}
      >
        {copied ? <Check className="w-4 h-4" /> : <Link2 className="w-4 h-4" />}
        <span>{copied ? "Copied!" : "Copy link"}</span>
      </button>
    </div>
  );
};
