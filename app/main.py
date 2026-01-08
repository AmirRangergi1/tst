import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import logging
from typing import List, Tuple, Optional

import pdfplumber
import pandas as pd
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import numpy as np

app = FastAPI(title="pdf-to-excel-service")
app.mount("/static", StaticFiles(directory="web/static"), name="static")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@app.get("/")
def root():
    return RedirectResponse(url='/static/index.html')

@app.get('/health')
def health():
    return {"status": "ok"}

MAX_BYTES = 100 * 1024 * 1024  # 100 MB
executor = ThreadPoolExecutor(max_workers=4)

# Load optional heavy deps at startup
try:
    import camelot
    HAS_CAMELOT = True
    logger.info("✓ Camelot available for advanced table detection")
except Exception as e:
    HAS_CAMELOT = False
    logger.warning(f"⚠ Camelot not available: {type(e).__name__}. Will use pdfplumber.")

try:
    from paddleocr import PaddleOCR
    ocr_engine = PaddleOCR(use_angle_cls=True, lang='en')
    HAS_PADDLE_OCR = True
    logger.info("✓ PaddleOCR loaded successfully")
except Exception as e:
    HAS_PADDLE_OCR = False
    ocr_engine = None
    logger.warning(f"⚠ PaddleOCR not available: {type(e).__name__}. Will use Tesseract.")

try:
    import pytesseract
    HAS_TESSERACT = True
    logger.info("✓ pytesseract available as OCR fallback")
except Exception as e:
    HAS_TESSERACT = False
    logger.warning(f"⚠ pytesseract not available: {type(e).__name__}. OCR disabled.")

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
    logger.info("✓ pdf2image available for full-page OCR")
except Exception as e:
    HAS_PDF2IMAGE = False
    logger.warning(f"⚠ pdf2image not available: {type(e).__name__}")


def save_upload_to_disk(upload_file: UploadFile, dst_path: str) -> int:
    """Stream upload to disk and enforce MAX_BYTES limit."""
    total = 0
    with open(dst_path, "wb") as f:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise HTTPException(status_code=413, detail="File too large (limit 100MB)")
            f.write(chunk)
    return total


def extract_tables_camelot(pdf_path: str, page_num: int) -> List[pd.DataFrame]:
    """Try Camelot lattice and stream flavors for table extraction."""
    if not HAS_CAMELOT:
        return []
    try:
        # Try lattice first (best for bordered tables)
        tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor='lattice')
        if tables:
            return [t.df for t in tables]
        # Fall back to stream (best for space-based tables)
        tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor='stream')
        if tables:
            return [t.df for t in tables]
    except Exception as e:
        logger.debug(f"Camelot extraction failed on page {page_num}: {e}")
    return []


def extract_tables_pdfplumber(page) -> List[pd.DataFrame]:
    """Extract tables using pdfplumber's native method."""
    try:
        tables = page.extract_tables()
        if tables:
            dfs = []
            for table in tables:
                if len(table) > 1:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    dfs.append(df)
            return dfs
    except Exception as e:
        logger.debug(f"pdfplumber table extraction failed: {e}")
    return []


def extract_text_pdfplumber(page) -> str:
    """Extract text with pdfplumber."""
    try:
        text = page.extract_text() or ""
        return text
    except Exception:
        return ""


def ocr_with_paddle(image: Image.Image) -> str:
    """Use PaddleOCR for high-accuracy text recognition."""
    if not HAS_PADDLE_OCR:
        return ""
    try:
        # Convert PIL image to numpy array
        img_np = np.array(image)
        result = ocr_engine.ocr(img_np, cls=True)
        text_lines = []
        if result:
            for line in result:
                for word_info in line:
                    text_lines.append(word_info[1])
        return "\n".join(text_lines)
    except Exception as e:
        logger.debug(f"PaddleOCR failed: {e}")
        return ""


def ocr_with_tesseract(image: Image.Image) -> str:
    """Fallback OCR with tesseract."""
    if not HAS_TESSERACT:
        return ""
    try:
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        logger.debug(f"Tesseract OCR failed: {e}")
        return ""


def page_to_image_high_res(page, dpi: int = 150) -> Optional[Image.Image]:
    """Convert PDF page to high-resolution image."""
    try:
        im = page.to_image(resolution=dpi)
        if hasattr(im, 'original'):
            img = im.original
        else:
            img = im
        if isinstance(img, bytes):
            img = Image.open(BytesIO(img))
        return img
    except Exception as e:
        logger.debug(f"Failed to convert page to image: {e}")
        return None


def process_page(pdf_path: str, page_num: int) -> Tuple[int, List[Tuple[str, pd.DataFrame]]]:
    """
    Process a single PDF page with multi-strategy extraction:
    1) Camelot lattice/stream for advanced table detection
    2) pdfplumber for native table/text extraction
    3) OCR (PaddleOCR + Tesseract fallback) for scanned/image-heavy pages
    
    Returns: (page_num, [(sheet_name, dataframe), ...])
    """
    rows = []
    try:
        with pdfplumber.open(pdf_path) as pdf_local:
            page = pdf_local.pages[page_num - 1]
            
            # Strategy 1: Camelot (if available)
            if HAS_CAMELOT:
                camelot_dfs = extract_tables_camelot(pdf_path, page_num)
                for t_idx, df in enumerate(camelot_dfs, start=1):
                    if not df.empty:
                        rows.append((f"p{page_num}_camelot_t{t_idx}", df))
            
            # Strategy 2: pdfplumber tables & text
            if not rows:
                pdfplumber_tables = extract_tables_pdfplumber(page)
                for t_idx, df in enumerate(pdfplumber_tables, start=1):
                    if not df.empty:
                        rows.append((f"p{page_num}_table_t{t_idx}", df))
            
            # Strategy 3: Extract plain text
            text = extract_text_pdfplumber(page)
            
            # Strategy 4: If no text and tables, try OCR
            if (not text or not text.strip()) and (not rows):
                logger.info(f"Page {page_num}: No text found, attempting OCR...")
                img = page_to_image_high_res(page, dpi=150)
                if img:
                    # Try PaddleOCR first (best quality)
                    if HAS_PADDLE_OCR:
                        ocr_text = ocr_with_paddle(img)
                        if ocr_text.strip():
                            text = ocr_text
                            logger.info(f"Page {page_num}: PaddleOCR extracted {len(text)} chars")
                    
                    # Fallback to Tesseract
                    if (not text or not text.strip()) and HAS_TESSERACT:
                        ocr_text = ocr_with_tesseract(img)
                        if ocr_text.strip():
                            text = ocr_text
                            logger.info(f"Page {page_num}: Tesseract extracted {len(text)} chars")
            
            # Create final row for this page
            if rows:
                # Add text as additional sheet if present
                if text and text.strip():
                    text_df = pd.DataFrame({"page": [page_num], "text": [text]})
                    rows.append((f"p{page_num}_text", text_df))
            else:
                # No tables: create text sheet
                text_df = pd.DataFrame({"page": [page_num], "content": [text or "[No content extracted]"]})
                rows.append((f"p{page_num}_text", text_df))
    
    except Exception as e:
        logger.error(f"Page {page_num} processing failed: {e}")
        err_df = pd.DataFrame({"page": [page_num], "error": [str(e)]})
        rows = [(f"p{page_num}_error", err_df)]
    
    return (page_num, rows)


def convert_pdf_to_excel_bytes(pdf_path: str) -> BytesIO:
    """
    Advanced multi-strategy PDF→Excel converter with parallel page processing.
    
    Strategies per page (in order):
    1. Camelot (lattice/stream) for bordered & space-based tables
    2. pdfplumber for native table extraction
    3. PaddleOCR for scanned/image pages (high accuracy, no GPU)
    4. Tesseract OCR as fallback
    
    Returns in-memory XLSX buffer.
    """
    out = BytesIO()
    
    # Determine page count
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
    
    logger.info(f"Processing {total_pages} pages with advanced strategies...")
    
    num_workers = min(4, (os.cpu_count() or 2))
    results = []
    
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(process_page, pdf_path, page_num): page_num
            for page_num in range(1, total_pages + 1)
        }
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
    
    # Sort by page number to maintain order
    results.sort(key=lambda x: x[0])
    
    # Write all sheets to Excel
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for page_num, rows in results:
            for sheet_name, df in rows:
                # Excel sheet names are limited to 31 chars
                safe_name = sheet_name[:31]
                try:
                    df.to_excel(writer, sheet_name=safe_name, index=False)
                except Exception as e:
                    logger.warning(f"Failed to write {safe_name}: {e}")
    
    out.seek(0)
    logger.info(f"✓ Conversion complete: {total_pages} pages processed")
    return out


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    """Convert uploaded PDF to Excel with streaming response."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    tmpdir = tempfile.mkdtemp(prefix="upload_")
    dst = os.path.join(tmpdir, file.filename)
    try:
        # Save with streaming to enforce size limit
        save_upload_to_disk(file, dst)

        # Offload conversion to thread pool
        from asyncio import get_running_loop
        loop = get_running_loop()
        out_buf = await loop.run_in_executor(executor, convert_pdf_to_excel_bytes, dst)

        headers = {
            "Content-Disposition": f'attachment; filename="{os.path.splitext(file.filename)[0]}.xlsx"'
        }
        return StreamingResponse(
            out_buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

