FROM python:3.11-slim

WORKDIR /app

# Require Anthropic key at build time so image embeds it as env
ARG ANTHROPIC_API_KEY
ENV ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
RUN test -n "$ANTHROPIC_API_KEY" || (echo "ANTHROPIC_API_KEY build arg is required" >&2; exit 1)

# System deps (optionally add build tools if packages require compilation)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better cache hits
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src ./src
COPY agent.log ./agent.log

EXPOSE 8000

# Start the API
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
