# ==============================================================================
# Octopus Agent: Production Container for Railway / Render / Cloud VPS
# Includes Python 3.11, FFmpeg, yt-dlp, and FastAPI 24/7 Background Workers
# ==============================================================================

FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr and writing bytecode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies: FFmpeg, curl, git, build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Verify FFmpeg installation
RUN ffmpeg -version

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure storage, output, assets, and logs directories exist
RUN mkdir -p storage output assets logs

# Expose default HTTP port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/telegram/status || exit 1

# Start Uvicorn on dynamic cloud PORT (defaults to 8000)
CMD ["sh", "-c", "python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
