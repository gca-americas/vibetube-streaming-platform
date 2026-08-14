#!/bin/bash
# Starts the backend and the Vite dev server together, and stops both on Ctrl-C.
#
# Development deliberately runs two processes: Vite serves the frontend with
# hot reload and proxies /api to the backend. The single-container layout is
# for deployment -- see `docker build` in README.md to run that locally.
set -e

cd "$(dirname "$0")"

export ADMIN_TOKEN="${ADMIN_TOKEN:-local-admin-token}"

if [ ! -d backend/venv ]; then
  echo "-> Creating backend virtualenv..."
  python3 -m venv backend/venv
  ./backend/venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "-> Installing frontend dependencies..."
  (cd frontend && npm install)
fi

# Stop both halves when either exits, so Ctrl-C never leaves a stray server
# holding port 8000.
cleanup() {
  trap - EXIT INT TERM
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "-> Starting backend on http://127.0.0.1:8000"
(cd backend && ./venv/bin/python main.py) &
BACKEND_PID=$!

echo "-> Starting frontend on http://localhost:5173"
(cd frontend && npm run dev) &
FRONTEND_PID=$!

wait -n "$BACKEND_PID" "$FRONTEND_PID"
