# Mock Strands Agent - local development only. Replace with a real agent
# before deploying.

# Same public Chainguard Python dev image as the worker (currently Python 3.15).
FROM cgr.dev/chainguard/python:latest-dev

# Switch to root user to install dependencies
USER root

# Set working directory
WORKDIR /app

# Install dependencies into a virtual environment
COPY requirements.txt .
RUN python -m venv /app/venv \
    && /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=nonroot:nonroot . .

# Switch to the image's built-in non-root user
USER nonroot

ENV PATH="/app/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Health check (the image has no curl, so use Python)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=2)"]

# Base image sets ENTRYPOINT ["python"]; clear it so CMD runs directly
ENTRYPOINT []
CMD ["python", "main.py"]
