# docker/Dockerfile
# Base image - choose a Python version that matches your python_requires in setup.py
# Using slim variant for smaller image size. Official Python images are multi-arch.
FROM python:3.10-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install git (if not already in the base image and needed for get_git_remote_url)
# and other system dependencies if any.
# For debian-based (like -slim):
RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
# For alpine-based images, it would be:
# RUN apk add --no-cache git openssh-client

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker layer caching for dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install unidiff==0.7.5 && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
# src/ will be copied to /app/src/, setup.py to /app/setup.py etc.
COPY src/ ./src/
COPY setup.py .
COPY MANIFEST.in .
# If you add a top-level version.py or similar, copy it too.

# Install the application
# This makes the 'drone-ai-pr-reviewer' command available
RUN pip install --no-cache-dir .

# Specify the user to run the application (optional, good practice)
# RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
# USER appuser

# Entrypoint for the Drone plugin
# This will execute the console_script 'drone-ai-pr-reviewer' defined in setup.py
ENTRYPOINT ["drone-ai-pr-reviewer"]

# Default command (can be empty if ENTRYPOINT is sufficient)
# CMD []