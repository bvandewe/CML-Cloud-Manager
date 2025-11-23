# Dockerfile for Cml Cloud Manager Application

# Stage 1: Build UI
FROM node:20 AS ui-build
WORKDIR /app/src/ui
# Copy package files first for caching
COPY src/ui/package*.json ./
RUN npm ci
# Copy the rest of the UI source code
COPY src/ui .
# Build the UI
# This outputs to /app/static (relative to /app/src/ui is ../../static)
RUN npm run build

# Stage 2: Python App
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy Poetry files
COPY pyproject.toml poetry.lock* ./

# Install Poetry and dependencies
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root

# Copy application code
COPY . .

# Copy built UI assets from ui-build stage
COPY --from=ui-build /app/static /app/static

# Set Python path to include src directory
ENV PYTHONPATH=/app/src:$PYTHONPATH

# Expose port
EXPOSE 8000

# Run the application from /app with PYTHONPATH set
# IMPORTANT: --workers 1 is required because background jobs (APScheduler)
# are NOT multi-worker safe. Multiple workers would cause duplicate job execution.
# For horizontal scaling, deploy multiple containers with 1 worker each.
CMD ["sh", "-c", "cd /app/src && uvicorn main:create_app --factory --host 0.0.0.0 --port 8000 --workers 1"]
