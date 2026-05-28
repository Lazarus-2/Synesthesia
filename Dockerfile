FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose API port
EXPOSE 8000

# Default command (can be overridden by docker-compose for worker)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
