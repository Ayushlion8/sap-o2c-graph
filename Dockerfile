FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy everything
COPY . .

# Install system deps (optional but safe)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Setup Python
WORKDIR /app/backend
RUN python -m venv venv
RUN . venv/bin/activate && pip install --no-cache-dir -r requirements.txt

# Go back
WORKDIR /app

# Expose port
EXPOSE 8000

# Start app
CMD ["bash", "start.sh"]