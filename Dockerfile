# Multi-stage build for Smart-Chunking Web-based Log Analysis
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
RUN mkdir -p /app/logs /app/output /app/.cache /app/temp && \
    chmod -R 775 /app/logs /app/output /app/.cache /app/temp && \
    chmod 775 /app

# Now switch to a non-root user
USER 1001

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies including Flask
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir flask && \
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

# LLM Configuration defaults (can be overridden)
ENV API_KEY=""
ENV MODEL_NAME="gpt-3.5-turbo"
ENV ENDPOINT_URL="https://api.openai.com/v1"

# Expose web server port
EXPOSE 8080

# Health check for web server
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Default command - run the web server
CMD ["python", "start_web_server.py", "--host", "0.0.0.0", "--port", "8080"]