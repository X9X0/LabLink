# Dockerfile for LabLink Server
FROM python:3.12-slim

LABEL maintainer="LabLink Project"
LABEL version="0.10.0"
LABEL description="Laboratory Equipment Control Server"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libusb-1.0-0 \
    udev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY server/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server/ .

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/states

# Expose ports
# 8000: REST API
# 8001: WebSocket
EXPOSE 8000 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=3)" || exit 1

# Environment variables
ENV LABLINK_SERVER_NAME="LabLink Server" \
    LABLINK_LOG_LEVEL="INFO" \
    LABLINK_HOST="0.0.0.0" \
    LABLINK_API_PORT="8000" \
    LABLINK_WS_PORT="8001"

# Run as non-root user
RUN useradd -m -u 1000 lablink && \
    chown -R lablink:lablink /app

USER lablink

# Start server
CMD ["python", "main.py"]
