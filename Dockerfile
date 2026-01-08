FROM python:3.11-slim

# Install system deps for PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    poppler-utils \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy minimal requirements first (faster builds)
COPY requirements-minimal.txt .
RUN pip install --no-cache-dir -r requirements-minimal.txt

# Copy optional heavy deps requirements
COPY requirements.txt .

# Try to install optional deps but don't fail if they fail
RUN pip install --no-cache-dir -r requirements.txt || echo "⚠ Some optional deps failed (OK for basic operation)" 

# Copy application code
COPY . /app

ENV PYTHONUNBUFFERED=1
ENV PYTESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
