# Databricks notebook source
# ================================================================================================
# MODULE 03 — PDF OCR / LAYOUT EXTRACTION + TEXT CHUNKING
# Ports: 01_PDF_EXTRACTION.sql STEP 8 (LOAD_RAW_PDFS) and STEP 9 (CREATE_TEXT_CHUNKS)
#
# Snowflake used AI_PARSE_DOCUMENT (OCR mode + LAYOUT mode) against an external S3 stage.
# Databricks has no exact equivalent tied to a Volume, so this module uses open-source
# `pdfplumber` for text + per-page extraction, which fully covers non-scanned PDFs (the
# large majority of contracts). For scanned/image-only PDFs it falls back to `pytesseract`
# OCR automatically, page by page, so the module degrades gracefully instead of failing.
#
# pip installs are declared at the top of the notebook (cluster-scoped libraries also work).
# ================================================================================================

# MAGIC %pip install pdfplumber pytesseract pdf2image --quiet
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../00_setup/00_config

# COMMAND ----------

import io
import uuid
import math
import pdfplumber
from pyspark.sql import Row
from pyspark.sql import functions as F

RAW = f"{CATALOG}.{RAW_SCHEMA}"
PIPELINE_RUN_ID = str(uuid.uuid4())


def _try_ocr_page(page_image):
    """Fallback OCR for image-only pages. Returns '' if pytesseract/poppler unavailable."""
    try:
        import pytesseract
        return pytesseract.image_to_string(page_image) or ""
    except Exception:
        return ""


def extract_pdf(path: str, file_name: str):
    """Extract full text + per-page char counts from one PDF. Falls back to OCR per page
    when a page yields no text layer (i.e. scanned page)."""
    full_text_parts = []
    page_char_counts = []
    used_ocr = False

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if len(text.strip()) < 20:
                # Likely a scanned page -> try OCR fallback
                try:
                    img = page.to_image(resolution=200).original
                    ocr_text = _try_ocr_page(img)
                    if len(ocr_text.strip()) > len(text.strip()):
                        text = ocr_text
                        used_ocr = True
                except Exception:
                    pass
            full_text_parts.append(text)
            page_char_counts.append(len(text))

    full_text = "\n".join(full_text_parts)
    return full_text, len(pdf.pages) if 'pdf' in dir() else len(page_char_counts), page_char_counts, used_ocr


# ------------------------------------------------------------------------------------------
# STEP 1 — walk the volume for PDFs and OCR/extract each one
# ------------------------------------------------------------------------------------------
pdf_dir = f"{VOLUME_PATH}/contracts/pdf"
try:
    pdf_files = [f for f in dbutils.fs.ls(pdf_dir) if f.name.lower().endswith(".pdf")]
except Exception:
    pdf_files = []

rows = []
for f in pdf_files:
    local_path = f.path.replace("dbfs:", "")
    try:
        text, page_count_layout, page_char_counts, used_ocr = extract_pdf(local_path, f.name)
        ocr_status = "SUCCESS" if text and len(text.strip()) > 0 else "FAILED"
    except Exception as e:
        text, page_count_layout, page_char_counts, used_ocr = "", None, [], False
        ocr_status = "FAILED"

    char_count = len(text)
    page_count_estimated = max(math.ceil(char_count / 800.0), 1)
    page_count_final = page_count_layout if page_count_layout else page_count_estimated
    density = min(char_count / max(page_count_final * 800.0, 1), 1.0)
    is_scanned = density < 0.4

    rows.append(Row(
        file_name=f.name,
        file_size=int(f.size),
        last_modified=None,  # dbutils FileInfo has no reliable mtime across clouds; left NULL
        file_url=f.path,
        ocr_text=text,
        parsed_json=None,
        document_page_count=page_count_layout,
        document_page_count_estimated=page_count_estimated,
        document_page_count_final=page_count_final,
        text_char_count=char_count,
        text_density_score=float(density),
        is_likely_scanned=bool(is_scanned),
        ocr_engine_version="pdfplumber+pytesseract v1 (Databricks)",
        ocr_status=ocr_status,
        pipeline_run_id=PIPELINE_RUN_ID,
        record_source="PDF_CONTRACT_PIPELINE",
    ))

if rows:
    raw_pdfs_df = spark.createDataFrame(rows).withColumn("ingestion_timestamp", F.current_timestamp())
    raw_pdfs_df.write.mode("overwrite").saveAsTable(f"{RAW}.raw_contract_pdfs")
    print(f"RAW_CONTRACT_PDFS loaded: {raw_pdfs_df.count()} rows "
          f"({raw_pdfs_df.filter('ocr_status=\"SUCCESS\"').count()} SUCCESS)")
else:
    print(f"No PDFs found under {pdf_dir} — skipping. Drop .pdf files there and re-run.")

# COMMAND ----------

# ------------------------------------------------------------------------------------------
# STEP 2 — CREATE_TEXT_CHUNKS
# Same page-estimation formula as the Snowflake procedure:
#   first_page = CEIL( chars_before_chunk / (doc_char_count / doc_page_count) )
#   last_page  = CEIL( chars_through_chunk_end / (doc_char_count / doc_page_count) )
# ------------------------------------------------------------------------------------------
CHUNK_SIZE = 4000

pdfs = spark.table(f"{RAW}.raw_contract_pdfs").filter(
    (F.upper(F.coalesce(F.col("ocr_status"), F.lit("FAILED"))) == "SUCCESS")
    & F.col("ocr_text").isNotNull()
    & (F.length(F.trim(F.col("ocr_text"))) > 0)
).collect()

chunk_rows = []
for r in pdfs:
    text = r["ocr_text"]
    doc_pages = max(r["document_page_count_final"] or 1, 1)
    doc_chars = max(r["text_char_count"] or 1, 1)
    chars_per_page = doc_chars / doc_pages
    total_len = len(text)
    n_chunks = math.ceil(total_len / CHUNK_SIZE) if total_len else 0
    source_doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, r["file_name"]))

    for i in range(n_chunks):
        start = i * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, total_len)
        chunk_text = text[start:end]
        if not chunk_text.strip():
            continue
        chunk_size = len(chunk_text)
        seq_start = start + 1
        seq_end = end

        first_page = max(math.ceil(seq_start / chars_per_page), 1) if chars_per_page else 1
        last_page = min(math.ceil(seq_end / chars_per_page), doc_pages) if chars_per_page else doc_pages

        if doc_pages == 1:
            page_range = "Page 1 of 1"
        elif first_page == last_page:
            page_range = f"Page {first_page} of {doc_pages}"
        else:
            page_range = f"Pages {first_page}-{last_page} of {doc_pages}"

        chunk_rows.append(Row(
            file_name=r["file_name"],
            pipeline_run_id=r["pipeline_run_id"],
            source_document_id=source_doc_id,
            chunk_id=i + 1,
            chunk_text=chunk_text,
            chunk_size=chunk_size,
            chunk_token_estimate=math.ceil(chunk_size / 4),
            chunk_sequence_start=seq_start,
            chunk_sequence_end=seq_end,
            total_chunks=n_chunks,
            document_page_count=doc_pages,
            first_page=first_page,
            last_page=last_page,
            page_range=page_range,
            text_density_score=min(chunk_size / max(doc_pages * 800.0, 1), 1.0),
            ocr_engine_version=r["ocr_engine_version"],
            ocr_status=r["ocr_status"],
            is_final_chunk=(i + 1 == n_chunks),
            is_truncated=(chunk_size >= 3990),
            needs_rechunking=(math.ceil(chunk_size / 4) > 3000),
        ))

if chunk_rows:
    chunks_df = spark.createDataFrame(chunk_rows).withColumn("load_timestamp", F.current_timestamp())
    chunks_df.write.mode("overwrite").saveAsTable(f"{RAW}.contract_text_chunks")
    print(f"CONTRACT_TEXT_CHUNKS loaded: {chunks_df.count()} rows across {len(pdfs)} documents")
else:
    print("No chunks produced (no successfully OCR'd PDFs).")
