FROM python:3.12-slim

WORKDIR /app

# System deps (WeasyPrint/PDF needs these; safe to include even if AI doesn't use them)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080