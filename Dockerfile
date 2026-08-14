# Vibetube runs as a single container: FastAPI serves both the API and the
# built React app, so there is no proxy hop and no second service to deploy.
# Build context is the repository root.

# Stage 1: build the React app
FROM node:20-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the Python service, with the built frontend baked in
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# main.py serves this directory and falls back to index.html for SPA routes.
COPY --from=frontend /build/dist ./static

ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
