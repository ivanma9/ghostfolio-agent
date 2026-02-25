# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.13-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy everything needed for install
COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install dependencies (no dev deps in production)
RUN uv sync --frozen --no-dev

# Copy built frontend assets
COPY --from=frontend-build /frontend/dist /app/static

EXPOSE 8000

CMD uv run uvicorn ghostfolio_agent.main:app --host 0.0.0.0 --port ${PORT:-8000}
