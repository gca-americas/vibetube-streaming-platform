# Vibeflix Video Streaming Platform

Vibeflix is a modern, unique, and fun video streaming platform. It features a cinematic neon/glow aesthetic and is built with React, Vite, TypeScript, and Tailwind CSS.

---

## Prerequisites

Before running the application, make sure you have the following installed:
- **Node.js** (v18.0.0 or higher recommended)
- **npm** (comes packaged with Node.js)

---

## Getting Started

Follow these steps to run the application locally:

### 1. Install Dependencies
Navigate to the project root directory and run:
```bash
npm install
```

### 2. Run the Development Server
To start the development server with hot-module replacement (HMR), run:
```bash
npm run dev
```
Once started, the terminal will display the local URL (usually `http://localhost:5173`). Open this link in your browser to view the application.

### 3. Build for Production
To compile and bundle the application for production deployment, run:
```bash
npm run build
```
This command runs the TypeScript compiler (`tsc`) and bundles the assets into the `dist/` directory using Vite.

### 4. Preview the Production Build
To preview the production build locally before deploying, run:
```bash
npm run preview
```

---

## Project Structure

Here is an overview of the key files and directories:
- `src/main.tsx` - Entry point that mounts the React application.
- `src/App.tsx` - Root application component.
- `src/components/` - Reusable UI components:
  - [`SearchBar.tsx`](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/src/components/SearchBar.tsx) - The centered glassmorphism search bar with animations.
  - [`VideoCard.tsx`](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/src/components/VideoCard.tsx) - Card layout representing individual videos.
- `src/data/mockVideos.json` - Source of truth for mock video metadata.
- `src/index.css` - Custom styling imports and Tailwind configuration.
- [`ARCHITECTURE.md`](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/ARCHITECTURE.md) - Detailed architecture document and design guidelines.
