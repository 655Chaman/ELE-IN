# PARANOIA FRAMEWORK: NEVER COPY .env INTO THIS IMAGE. NEVER HARDCODE SECRETS AS ENV INSTRUCTIONS. ALL SECRETS ARE INJECTED AT RUNTIME VIA CONTAINER ORCHESTRATION (K8s Secrets, Docker Compose environment).

# --- Builder Stage ---
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

# Install build dependencies if any are needed for Python packages
RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential && rm -rf /var/lib/apt/lists/*

# Create a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Runtime Stage ---
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Create a non-root user and setup directories
RUN useradd -m appuser && mkdir /app /ms-playwright && chown -R appuser:appuser /app /ms-playwright
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Install Playwright OS dependencies and Chromium as root
RUN playwright install --with-deps chromium && chown -R appuser:appuser /ms-playwright

# Copy application code
COPY core/ core/
COPY accounts/ accounts/
COPY campaigns/ campaigns/
COPY dashboard/ dashboard/
COPY inbox/ inbox/
COPY integrations/ integrations/
COPY knowledge/ knowledge/
COPY leads/ leads/
COPY backend/ backend/

# Ensure appuser owns the copied code
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD test -n "$SUPABASE_URL" || exit 1

EXPOSE 8000

CMD ["uvicorn", "core.backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--env-file", "backend/.env"]
