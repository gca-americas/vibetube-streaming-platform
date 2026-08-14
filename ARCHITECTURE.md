# Vibetube Video Streaming Platform - Architecture

Vibetube is a modern, unique, and fun video streaming platform. It is designed to be built in incremental phases, starting with a minimal, high-vibe user interface and scaling up to a complete distributed streaming service.

---

## Phase 1: Minimalist Search & Grid Main Page

For the initial phase, the application consists purely of a modern, dark-mode single-page frontend.

### 1. Technology Stack
* **Framework**: React 18 (Single Page Application, built with Vite)
* **Language**: TypeScript
* **Styling**: Tailwind CSS v4 (Cinematic dark theme with custom neon/spotlight gradients and modern layout)
* **Icon Library**: Lucide React (clean, lightweight icons)

### 2. File & Component Structure
```
vibetube-streaming-platform/
├── ARCHITECTURE.md          # Architectural plan and current design touchpoint
├── AUDIT_TRAIL.md           # Log of phases and design decisions
├── package.json             # NPM package configuration
├── vite.config.ts           # Vite bundler configuration
├── tsconfig.json            # TypeScript configuration
├── index.html               # Entry HTML page
└── src/
    ├── main.tsx             # React mount point
    ├── App.tsx              # Root component
    ├── index.css            # Custom utility classes and Tailwind imports
    ├── data/
    │   └── mockVideos.json  # Separate source of truth for mock video metadata
    └── components/
        ├── SearchBar.tsx    # Search input component with interactive design
        └── VideoCard.tsx    # Individual video representation card
```

### 3. Data Schema
The initial video dataset is loaded from `mockVideos.json` and follows this schema:
```typescript
interface Video {
  id: string;
  title: string;
  description: string;
  thumbnailUrl: string;
  videoUrl: string;
  duration: string;       // e.g., "12:34"
  views: number;
  uploadedAt: string;     // ISO-8601 string or simple humanized relative time
  channelName: string;
  channelAvatar: string;
}
```

### 4. Styling & Aesthetics
Unlike classic platform designs, Vibetube targets a "cinematic neon/glow" aesthetic:
* **Background**: Very dark canvas (`#08080a`) with a soft top-centered radial red/pink spotlight gradient (`rgba(229, 9, 20, 0.15)`).
* **Search Bar**: Centered, floating glassmorphism search input with a neon hover/focus accent and smooth scaling animations.
* **Cards**: Grid layout with rounded corners, subtle scaling hover states, and smooth image load transitions.
