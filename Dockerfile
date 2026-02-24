FROM python:3.13-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy everything needed for install
COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install dependencies (no dev deps in production)
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "ghostfolio_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
