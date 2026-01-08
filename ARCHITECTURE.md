# PDF to Excel - Advanced Converter
# خلاصه کل پروژه و معمارі

## 📁 ساختار فایل‌ها

```
tst/
├── app/
│   └── main.py              # FastAPI app with advanced PDF processing
├── web/
│   └── static/
│       └── index.html       # Single-page app (SPA) - UI
├── tests.py                 # Unit tests
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container image
├── docker-compose.yml       # Multi-container orchestration
├── nginx.conf              # Reverse proxy & load balancer config
├── .env.example            # Environment variables template
├── README.md               # Full documentation
└── ARCHITECTURE.md         # This file
```

## 🏗️ معماری

```
┌─────────────────────┐
│   Web Browser       │
│  (SPA - HTML/JS)    │
└──────────┬──────────┘
           │ HTTP/FormData (multipart)
           │ MAX: 100MB
           ▼
┌─────────────────────────────────┐
│   Nginx Reverse Proxy           │
│  (Port 80/443, SSL, Gzip, etc)  │
│  client_max_body_size: 100M     │
└──────────┬──────────────────────┘
           │ Proxy Pass (FastAPI)
           ▼
┌──────────────────────────────────────────────┐
│   FastAPI Application (uvicorn)              │
│  ┌──────────────────────────────────────┐    │
│  │ POST /convert                        │    │
│  │ 1. Receive file (streaming upload)   │    │
│  │ 2. Validate & save to temp           │    │
│  │ 3. Offload to ThreadPoolExecutor     │    │
│  └──────────────────────────────────────┘    │
│                                               │
│  ┌──────────────────────────────────────┐    │
│  │ PDF Processing Pipeline (per page)   │    │
│  │                                       │    │
│  │  Page → [1] Camelot lattice/stream   │    │
│  │       → [2] pdfplumber tables        │    │
│  │       → [3] Extract text             │    │
│  │       → [4] If empty: OCR            │    │
│  │                                       │    │
│  │  OCR Options (fallback chain):       │    │
│  │  a) PaddleOCR (CPU, high accuracy)   │    │
│  │  b) Tesseract (CPU, fallback)        │    │
│  │                                       │    │
│  │  Output: List[(sheet_name, DataFrame)]  │
│  └──────────────────────────────────────┘    │
│                                               │
│  ┌──────────────────────────────────────┐    │
│  │ Parallel Processing (ThreadPool)     │    │
│  │                                       │    │
│  │  Max Workers: min(4, cpu_count)      │    │
│  │  Process multiple pages concurrently │    │
│  │  Sort results by page number         │    │
│  │  Write to Excel (openpyxl)           │    │
│  └──────────────────────────────────────┘    │
│                                               │
│  ┌──────────────────────────────────────┐    │
│  │ Response                             │    │
│  │ StreamingResponse (XLSX bytes)       │    │
│  │ Content-Disposition: attachment      │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

## 🔄 جریان پردازش PDF

### Phase 1: Upload & Validation
- Multipart form-data with streaming
- Validate filename ends with `.pdf`
- Enforce 100MB limit (413 if exceeded)
- Save to temporary directory

### Phase 2: PDF Metadata
- Open PDF with pdfplumber
- Count pages
- Plan parallel processing

### Phase 3: Per-Page Processing (Parallel)
Each page goes through extraction strategies in order:

#### Strategy 1: Camelot Table Detection (Optional)
- Requires: `camelot-py[cv]`, ghostscript
- Flavors: lattice (bordered), stream (space-based)
- Output: `p{page}_camelot_t{table_index}` sheets
- Best for: Structured tabular data

#### Strategy 2: pdfplumber Native Tables
- Always available
- Extract tables from page geometry
- Output: `p{page}_table_t{index}` sheets
- Best for: Simple, well-formed tables

#### Strategy 3: Text Extraction
- pdfplumber text extraction
- Output: `p{page}_text` sheet if text found
- Best for: Text-heavy documents

#### Strategy 4: OCR Fallback (if no text)
When page has no extracted text but contains information:

**Option A: PaddleOCR** (Preferred)
- Requires: `paddleocr` package
- CPU-friendly (no GPU needed)
- High accuracy (~99% for clear text)
- Supports English + Chinese + multi-lingual
- Output: `p{page}_text` sheet with OCR results

**Option B: Tesseract OCR** (Fallback)
- Requires: `pytesseract`, `tesseract-ocr` binary
- Lower accuracy than Paddle
- Lighter resource footprint
- Output: `p{page}_text` sheet

### Phase 4: Excel Writing
- Create openpyxl writer (in-memory BytesIO)
- Write pages in order (deterministic)
- Sheet names clamped to 31 chars
- Handle failures gracefully (log + continue)

### Phase 5: Response
- Stream binary XLSX content
- Set Content-Disposition: attachment
- Browser downloads as `{original_name}.xlsx`
- Clean up temp files

## 💡 استراتژی‌های خطا (Error Handling)

### Per-Page Level
- Strategy falls back to next one if fails
- Page processing errors don't stop conversion
- Failed page marked with `p{page}_error` sheet

### System Level
- Optional dependencies checked at startup
- Missing deps logged but don't crash
- Graceful degradation: converter works with subset of features

### Size Limits
- 100MB upload hard limit (enforced at stream)
- 413 Payload Too Large response

### Timeouts
- Nginx: 300 second read/write timeout for long PDFs
- Per-page processing: concurrent (not sequential)

## 📊 أداء (Performance)

### Optimizations
1. **Parallel Processing**: Pages processed on ThreadPool (4 workers)
2. **Streaming Upload**: Chunk-based, memory-efficient
3. **Streaming Response**: XLSX written to BytesIO, not temp file
4. **Lazy Deps**: Heavy packages imported on-demand
5. **Gzip**: Nginx compresses text responses

### Benchmarks (Estimated)
- **Small PDF (1-5 pages, text)**: 1-2 seconds
- **Medium PDF (10-20 pages, tables)**: 3-5 seconds
- **Large scanned PDF (50 pages, OCR)**: 30-60 seconds
- **Parallel speedup**: ~3-4x with 4 workers on quad-core CPU

## 🚀 Deployment Options

### Local Development
```bash
uvicorn app.main:app --reload --port 8000
```

### Docker (Single Container)
```bash
docker build -t pdf2xlsx .
docker run -p 8000:8000 pdf2xlsx
```

### Docker Compose (Recommended)
```bash
docker-compose up -d
# Nginx on :80, FastAPI on :8000 (internal)
```

### Cloud (Kubernetes, Heroku, AWS)
1. Push Docker image to registry
2. Deploy container with 1-2GB RAM
3. Set environment: `PORT=8000`
4. Reverse proxy (Nginx/ELB) with `client_max_body_size 100M`

## 🔐 أمان

### Built-in
- File type validation (.pdf only)
- Size limit enforcement
- Temporary file cleanup
- Error details minimal in responses

### Recommended (Production)
- HTTPS/TLS (nginx config included)
- Rate limiting (implement at reverse proxy)
- Input sanitization (filenames)
- Monitoring & logging (structured logs)
- Regular dependency updates

## 📈 آینده (Future Enhancements)

1. **Async Job Queue**
   - Celery + Redis for long-running conversions
   - WebSocket progress updates
   - Job persistence

2. **Advanced OCR**
   - LayoutParser for document structure
   - Detectron2 for table detection
   - Multi-language support

3. **Post-Processing**
   - Column auto-width
   - Format detection (currency, dates)
   - Sheet merging strategies

4. **Monitoring**
   - Prometheus metrics
   - Structured logging (JSON)
   - Error alerting

5. **Testing**
   - Pytest fixtures for sample PDFs
   - Integration tests
   - CI/CD (GitHub Actions)

## 📚 References

- FastAPI: https://fastapi.tiangolo.com/
- pdfplumber: https://github.com/jsvine/pdfplumber
- Camelot: https://camelot-py.readthedocs.io/
- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR
- Tesseract: https://github.com/tesseract-ocr/tesseract
- openpyxl: https://openpyxl.readthedocs.io/

---

**Version**: 2.0 (Advanced Edition)
**Last Updated**: Jan 8, 2026
**Author**: AI Assistant
