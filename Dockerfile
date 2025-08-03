# Multi-stage build for Smart-Chunking Detection Engine
FROM registry.redhat.io/ubi9/python-39:latest AS base

# Use root for installing dependencies and setting permissions
USER root

# Install system dependencies
RUN dnf update -y && \
    dnf install -y gcc gcc-c++ make git curl --allowerasing && \
    dnf clean all

# Set working directory
WORKDIR /app

# Create necessary directories and set permissions
RUN mkdir -p /app/logs /app/output /app/.cache && \
    chmod -R 775 /app/logs /app/output /app/.cache

# Now switch to a non-root user
USER 1001

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download en_core_web_sm

# Copy source code and configuration
COPY src/ ./src/
COPY config/ ./config/
COPY *.py ./

# Set environment variables
ENV PYTHONPATH=/app
ENV TRANSFORMERS_CACHE=/app/.cache/transformers
ENV HF_HOME=/app/.cache/huggingface
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=8080

# Expose API port
EXPOSE 8080

# Test container environment during build
RUN python container_test.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command - run the web server using direct execution
CMD ["python", "src/web_server.py", "--host", "0.0.0.0", "--port", "8080"]