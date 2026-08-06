# Vibetube Audit Trail

## Phase 1: Minimalist Search & Grid Main Page (2026-08-03)
- **Initialized project framework**: Created standard React + TypeScript + Vite configurations (`package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`).
- **Configured visual branding & styles**: Integrated Google Fonts (`Archivo`, `Montserrat`) and configured Tailwind v4 with a custom cinema dark mode theme (`bg-stage`, `bg-card`, and neon highlights). Added a `.stage-vignette` styling to render a red spotlight gradient.
- **Implemented separate data storage**: Created `mockVideos.json` to store static metadata for 8 initial video models.
- **Downloaded and stored local media assets**: Saved all remote thumbnails and channel avatars to local folders (`public/images/thumbnails` and `public/images/avatars`) using verified high-availability Unsplash IDs, updating `mockVideos.json` to reference these local paths for 100% availability.
- **Developed UI components**:
  - `SearchBar.tsx`: A glassmorphism search input centered at the top of the page, highlighted by a subtle neon hover and focus gradient.
  - `VideoCard.tsx`: Standardized container for display titles, channel avatars, view count formatting, and custom play-on-hover overlays.
  - `App.tsx`: Main layout wrapper integrating the search state machine, computing filters, and handling empty result flows.
- **Verification**: Built and packaged all production assets successfully using standard bundler pipelines (`npm run build`).

## Phase 2: Implement the video player (2026-08-03)
- **Developed Video Playback View**: Created `VideoPlayerModal.tsx` as a centered single-column overlay modal using Tailwind CSS glassmorphic borders and custom fade-in transitions.
- **Wired up Click Handlers**: Modified `VideoCard.tsx` and `App.tsx` to handle card selection and trigger playback state.
- **Updated Video URLs**: Configured valid, high-availability public domain video streams from `w3schools.com` and `w3.org` in `mockVideos.json` to resolve the 403 Forbidden issues.
- **Created Setup Documentation**: Added `README.md` with instructions on installing dependencies and running the local development and production environments.
- **Verification**: Built production assets successfully.

## Phase 3: Stand up the backend (2026-08-03)
- **Decoupled Application Structure**: Restructured workspace directories into discrete `/frontend` and `/backend` packages.
- **Implemented Python FastAPI Backend**: Coded a new backend application in `backend/main.py` using `fastapi` and `uvicorn`, loading `mockVideos.json` locally and exposing the `GET /api/videos` query endpoint.
- **Configured Vite Dev Proxy**: Set up Vite proxy rules in `frontend/vite.config.ts` to redirect client-side API requests to port `8000`.
- **Integrated React Fetch Requests**: Configured `App.tsx` state models (`videos`, `loading`, `error`) to load data dynamically on mount using browser `fetch`.
- **Verification**: Verified endpoint responses via cURL and compiled the frontend production build without errors.

## Phase 4: SQLite Database Integration (2026-08-03)
- **Database Layer Transition**: Migrated backend data storage from direct file reads of `mockVideos.json` to a local SQLite database (`vibetube.db`).
- **Database Code Modularization**: Created a separate `database.py` file to isolate database connections, table creation, and seed queries, importing them cleanly in `main.py`.
- **Automated Seeding on Startup**: Implemented `init_db()` in `backend/database.py` to create the schema and seed the initial dataset on first boot.
- **Dynamic SQL Querying**: Updated the `GET /api/videos` endpoint to query the SQLite table directly.
- **Excluded Binary DBs from Git**: Appended `*.db` to `.gitignore`.
- **Verification**: Successfully fetched seeded video records from the SQLite database.

## Phase 5: Video Upload Capability (2026-08-03)
- **Created Video POST Endpoint**: Developed `POST /api/videos` in `backend/main.py` utilizing Pydantic models to validate metadata and insert new records into the SQLite database.
- **Created Upload Modal Form**: Added `UploadModal.tsx` in `frontend/src/components/` allowing users to input title, description, video stream, and creator credentials.
- **Wired UI Refresh**: Updated `App.tsx` to include the "+" button in the header, state hooks to toggle the upload modal, and dynamic server re-fetching on successful uploads.
- **Verification**: Tested successful JSON insertions via cURL and verified Vite client production builds compiled cleanly.

## Phase 6: Binary File Uploads (2026-08-03)
- **Implemented Local File Uploads**: Modified `POST /api/videos` to accept binary `UploadFile` payloads via `multipart/form-data` and write them to a local `backend/uploads/` directory.
- **Added Static Video Serving**: Mounted the uploads directory as a static folder in FastAPI and added proxy routes for `/uploads` in `vite.config.ts`.
- **Created Frontend File Picker**: Refactored `UploadModal.tsx` to include a file picker and submit payloads using standard `FormData` objects.
- **Excluded Upload Binaries**: Appended `backend/uploads/` to `.gitignore`.
- **Verification**: Verified binary file persistence and client playback.

## Phase 7: Video Transcoding & HLS Streaming (2026-08-04)
- **Implemented Transcoder CLI**: Developed a Python Click CLI in `transcoder/cli.py` and `converter.py` using `ffmpeg` to transcode input files to HLS formats (480p, 720p, 1080p, and `master.m3u8` playlists) and standalone MP4 files.
- **Added HLS Server Types**: Configured FastAPI backend to explicitly register `.m3u8` (`application/x-mpegURL`) and `.ts` (`video/MP2T`) MIME types.
- **Integrated Frontend HLS Player**: Loaded `hls.js` from CDN in `index.html` and refactored `VideoPlayerModal.tsx` to dynamically attach the HLS parsing engine with a native Safari fallback.
- **Fixed Aspect-Ratio Video Scaling**: Bounded the HTML5 `<video>` tag within absolute constraints (`absolute inset-0`) in `VideoPlayerModal.tsx` to correct viewport overflow and letterbox vertical/portrait videos properly.
- **Verification**: Transcoded test movie `IMG_1735.MOV` successfully and verified correct MIME headers and layout scaling on local development servers.

## Phase 8: Firebase Authentication & User Management (2026-08-04)
- **Loaded Firebase compat library**: Included the Firebase App and Auth compat scripts from Google's CDN inside `index.html`.
- **Created Auth service with Mock mode**: Developed `firebase.ts` supporting standard auth callbacks, featuring a transparent `MockAuth` simulation that runs automatically in local environment if credentials are not configured, permitting offline testing.
- **Added RS256 JWT Verification**: Created `backend/auth.py` verifying Firebase ID tokens manually via base64url parsing, fetching/caching Google's certificates, and verifying RSA signatures using preinstalled `cryptography` library.
- **Upgraded Database Schema**: Modified `backend/database.py` to auto-migrate the SQLite schema on boot, adding `userId TEXT` column to the `videos` table.
- **Secured Upload Endpoint & UI Controls**: Enforced authentication on `POST /api/videos`, pre-populating upload details from user profiles. Conditionalized the header controls so the `+` upload button is only visible to logged-in users, adding Google login buttons to `AuthModal.tsx`.
- **Verification**: Verified React builds compiled cleanly via `npx tsc --noEmit` and verified both Google Sign-in and email logins mock successfully in offline mode.
