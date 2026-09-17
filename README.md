# Universal AI Media Processing Pipeline

A reusable FastAPI backend for processing **video, audio,
images/screenshots, and PDF files** through one common media-processing
architecture.

The pipeline accepts uploaded media and permitted direct media URLs,
detects the actual media type, validates and normalizes the input,
performs deterministic extraction, preserves provenance, optionally
applies AI reasoning, manages artifacts, caches repeated content, and
returns a stable normalized structure suitable for downstream AI
systems.

## Core idea

``` text
Input
  ↓
Acquire
  ↓
Detect
  ↓
Validate
  ↓
SHA-256 Fingerprint / Cache Check
  ↓
Select Modality Processor
  ↓
Deterministic Extraction
  ↓
Artifact Management
  ↓
Optional AI Reasoning
  ↓
Normalize + Validate
  ↓
Cache Result
  ↓
Return
```

The architecture deliberately uses **one common pipeline with
modality-specific processors**, rather than four separate applications.

## Supported media

  -----------------------------------------------------------------------
  Media                               Main processing
  ----------------------------------- -----------------------------------
  Video                               FFprobe metadata, FFmpeg
                                      normalization, audio extraction,
                                      timestamped transcription, frame
                                      sampling, OCR where useful

  Audio                               Validation, speech-audio
                                      normalization, timestamped
                                      transcription

  Image / Screenshot                  Image validation/normalization,
                                      OCR, confidence and bounding-box
                                      information

  PDF                                 Metadata/page inspection, native
                                      text extraction, scanned-page OCR,
                                      embedded image extraction,
                                      page-level provenance
  -----------------------------------------------------------------------

### Input methods

-   File upload
-   Permitted direct HTTPS media URL

URL ingestion is limited to media the user is authorized/permitted to
access. The system does **not** bypass DRM, authentication, paywalls,
private access controls, or platform restrictions.

## Architecture

``` text
                    ┌─────────────────────────┐
                    │       Input Layer       │
                    │   Upload / Direct URL   │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Acquisition + Detection │
                    │ Download / MIME /       │
                    │ Container inspection     │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Validation + Fingerprint │
                    │ Integrity / limits /     │
                    │ SHA-256 / cache          │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │      Normalization      │
                    │ Standard processing     │
                    │ formats / timestamps    │
                    └────────────┬────────────┘
                                 ↓
                 ┌───────────────┼───────────────┐
                 ↓               ↓               ↓
             Video            Audio        Image / PDF
                 └───────────────┼───────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Deterministic Extraction│
                    │ + Evidence / Provenance │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │    Optional AI Layer    │
                    │ Topics / Summary /       │
                    │ Semantic organization    │
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Schema Validation +     │
                    │ Artifact Storage + Cache│
                    └────────────┬────────────┘
                                 ↓
                    ┌─────────────────────────┐
                    │ Normalized Media Result │
                    └─────────────────────────┘
```

The orchestrator coordinates the lifecycle but keeps modality-specific
extraction logic inside the processors.

## Repository structure

``` text
universal-media-pipeline/
│
├── .gitignore
│
└── backend/
    ├── app/
    │   ├── main.py
    │   │
    │   ├── api/
    │   │   ├── media.py
    │   │   └── reasoning.py
    │   │
    │   ├── core/
    │   │   └── config.py
    │   │
    │   ├── models/
    │   │   ├── media.py
    │   │   ├── processing.py
    │   │   └── provenance.py
    │   │
    │   ├── pipeline/
    │   │   ├── acquisition.py
    │   │   ├── detector.py
    │   │   ├── normalizer.py
    │   │   ├── orchestrator.py
    │   │   └── validator.py
    │   │
    │   ├── processors/
    │   │   ├── audio.py
    │   │   ├── base.py
    │   │   ├── image.py
    │   │   ├── pdf.py
    │   │   ├── registry.py
    │   │   └── video.py
    │   │
    │   ├── extractors/
    │   │   ├── ocr.py
    │   │   └── transcription.py
    │   │
    │   ├── reasoning/
    │   │   ├── llm.py
    │   │   ├── summarizer.py
    │   │   └── topics.py
    │   │
    │   ├── schemas/
    │   │   ├── normalized.py
    │   │   └── reasoning.py
    │   │
    │   └── services/
    │       ├── artifacts.py
    │       ├── cache.py
    │       ├── jobs.py
    │       └── llm_service.py
    │
    └── requirements.txt
```

Generated runtime data is intentionally excluded from Git:

``` text
backend/.env
backend/storage/cache/
backend/storage/artifacts/
backend/storage/temp/
backend/app/**/__pycache__/
```

## Technology stack

-   **Python**
-   **FastAPI**
-   **Pydantic / pydantic-settings**
-   **HTTPX**
-   **Pillow**
-   **PyMuPDF**
-   **pytesseract / Tesseract OCR**
-   **Whisper**
-   **FFmpeg / FFprobe**
-   **SHA-256 via Python hashlib**
-   **Local filesystem storage for the MVP**
-   **OpenAI-compatible client connected to the configured LLM /
    FreeLLMAPI service**

## Local setup

### 1. Clone the repository

``` bash
git clone https://github.com/mayurbhati2110-Ak/universal-media-pipeline.git
cd universal-media-pipeline/backend
```

### 2. Create a virtual environment

Windows:

``` cmd
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

``` bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

``` bash
pip install -r requirements.txt
```

The current application code also imports the OpenAI-compatible Python
client and `python-dotenv`. If they are not already installed in the
environment, install them with:

``` bash
pip install openai python-dotenv
```

### 4. Install external tools

The media processors rely on external tools/models:

-   **FFmpeg and FFprobe** for media inspection, conversion, audio
    extraction, and video processing
-   **Tesseract OCR** for OCR
-   **Whisper** for speech transcription

Make sure the corresponding executables are available on `PATH`, or
configure the Tesseract executable through the application settings when
required.

### 5. Configure environment variables

Create:

``` text
backend/.env
```

Do **not** commit this file.

Current LLM configuration uses:

``` env
LLM_API_KEY=your_api_key
LLM_BASE_URL=your_openai_compatible_base_url
LLM_MODEL=auto
```

The application loads these values from `.env`.

## Run the backend

From the `backend` directory:

``` bash
uvicorn app.main:app --reload
```

The API will normally be available at:

``` text
http://127.0.0.1:8000
```

Interactive API documentation:

``` text
http://127.0.0.1:8000/docs
```

## API surface

The implemented API uses the `/api/media` prefix.

  --------------------------------------------------------------------------------------
  Method                  Endpoint                               Purpose
  ----------------------- -------------------------------------- -----------------------
  `POST`                  `/api/media/upload`                    Upload and process a
                                                                 media file

  `POST`                  `/api/media/url`                       Process an accessible
                                                                 direct media URL

  `GET`                   `/api/media/jobs/{job_id}`             Get job status and
                                                                 error information

  `GET`                   `/api/media/jobs/{job_id}/result`      Get the stored
                                                                 normalized result

  `GET`                   `/api/media/jobs/{job_id}/artifacts`   Get artifact metadata

  `GET`                   `/health`                              Health check

  `GET`                   `/`                                    Service information
  --------------------------------------------------------------------------------------

An additional reasoning router is included for the optional AI reasoning
functionality.

### Upload example

Using `curl`:

``` bash
curl -X POST "http://127.0.0.1:8000/api/media/upload" \
  -F "file=@sample.jpg"
```

The response contains a `job_id`, processing status, and the processing
result.

### URL example

``` bash
curl -X POST "http://127.0.0.1:8000/api/media/url" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://example.com/media/sample.mp4\"}"
```

The URL must point to directly accessible media and must satisfy the
application's URL/security restrictions.

## Job lifecycle

The MVP exposes these processing states:

  -----------------------------------------------------------------------
  State                               Meaning
  ----------------------------------- -----------------------------------
  `queued`                            Job has been accepted and is
                                      waiting to run

  `processing`                        Pipeline processing is in progress

  `completed`                         Required processing completed
                                      successfully

  `partial`                           Core processing succeeded but an
                                      optional/secondary stage failed

  `failed`                            A required stage failed and no
                                      usable normalized result was
                                      produced

  `cached`                            A compatible previously processed
                                      result was reused
  -----------------------------------------------------------------------

The current job store is in-memory, so job state is tied to the running
application process.

## Normalized output contract

The central output is `NormalizedMediaDocument`.

``` text
NormalizedMediaDocument
├── document_id
├── schema_version
├── media_type
├── source
│   ├── source_type
│   ├── filename / url
│   ├── content_hash
│   └── acquisition
├── metadata
│   ├── size
│   ├── duration / page_count / dimensions
│   ├── detected format
│   └── content hash
├── content
│   ├── segments
│   ├── evidence
│   ├── structured_elements
│   ├── topics
│   └── summary
├── artifacts
├── provenance
├── processing
│   ├── status
│   ├── stages
│   ├── cache_hit
│   └── warnings / errors
└── extra
```

The schema is versioned so downstream consumers can identify changes to
the normalized contract.

## Provenance

Provenance is a first-class part of the output.

The system is designed so extracted information can be traced back to
its source rather than being reduced to one untraceable text block.

Typical provenance fields include:

``` text
source_type
source_artifact
page
timestamp_start
timestamp_end
frame_number
bbox
extraction_method
```

Examples:

-   Video → timestamps and frame references
-   Audio → timestamps and speaker labels when available
-   Image → image artifact and OCR bounding box
-   PDF → page number and coordinates when available

AI-generated summaries and topics are based on extracted evidence. The
reasoning layer is instructed not to invent timestamps, pages, speakers,
facts, or source references.

## Deterministic extraction vs AI reasoning

The architecture intentionally separates factual extraction from
semantic interpretation.

### Deterministic processing

Used for:

-   Media/container detection
-   FFprobe metadata
-   FFmpeg conversion
-   PDF page extraction
-   OCR
-   Speech transcription
-   Timestamps
-   SHA-256 hashing
-   Pydantic validation

### AI reasoning

Used where semantic interpretation adds value:

-   Topic extraction
-   Semantic sectioning
-   Summarization
-   Meaningful grouping

The LLM receives structured evidence instead of raw media whenever
practical.

## Duplicate detection and caching

Every acquired file receives a SHA-256 content hash.

The cache uses the content hash to recognize previously processed
content and can reuse a compatible normalized result.

The architecture specification recommends a production-safe cache key
of:

``` text
content_hash
+
pipeline_version
+
processor_version
+
configuration_hash
```

The current MVP implements content-hash-based caching. Version-aware
cache invalidation is a production extension.

Content hash is authoritative for duplicate content because different
URLs can serve the same file, while the same URL can serve different
content over time.

## Artifact management

Derived artifacts are managed separately from the source input.

The current artifact manager stores generated artifacts under:

``` text
storage/artifacts/<document_id>/
```

Each stored artifact records:

-   Artifact ID
-   Artifact type
-   File path
-   MIME type
-   Size
-   SHA-256 hash
-   Additional metadata

Temporary files are kept under `storage/temp/` and are excluded from
Git.

## URL ingestion and security

The URL acquisition layer:

1.  Validates the URL scheme.
2.  Validates the destination host.
3.  Applies basic SSRF/network protections.
4.  Handles redirects explicitly.
5.  Applies timeout and maximum download-size limits.
6.  Streams downloads rather than loading the complete file into RAM.
7.  Calculates SHA-256 while downloading.
8.  Detects actual media type after acquisition.
9.  Validates the resulting file before expensive processing.

The system must only process media the user is authorized/permitted to
access.

It must not be used to bypass:

-   DRM
-   Authentication
-   Paywalls
-   Private access controls
-   Platform restrictions

## Failure handling

The pipeline prefers useful partial results over discarding successful
work.

For example:

``` text
Validation       ✓
Normalization    ✓
Transcription    ✓
OCR              ✗
```

can produce a `partial` result with an explicit OCR warning/error rather
than failing the complete media job.

Errors are represented with structured fields such as:

``` text
stage
code
message
recoverable
details
```

## Resource controls

The current configuration includes:

-   Maximum upload size: 500 MB
-   Maximum URL download size: 500 MB
-   Download timeout: 30 seconds
-   Maximum redirects: 5
-   HTTPS URL scheme restriction
-   Chunked media acquisition

The architecture also calls for configurable duration, page-count, and
resolution policies and careful temporary-storage management.

## Validation principles

The system does not trust only the filename extension or declared MIME
type.

It attempts to determine actual media type from file/content/container
information before selecting a processor.

Validation occurs before expensive operations, and generated normalized
output is also validated against the common schema.

## Current MVP scope

Implemented in the current backend:

-   Common pipeline/orchestrator
-   Video processor
-   Audio processor
-   Image/OCR processor
-   PDF processor
-   Direct URL acquisition
-   Upload acquisition
-   Media detection
-   Input validation
-   SHA-256 hashing
-   Content-based cache
-   Artifact manager
-   In-memory job/status handling
-   Normalized Pydantic output
-   Provenance/evidence models
-   Optional topic extraction
-   Optional summarization
-   Structured warnings/errors
-   FastAPI endpoints

## Known limitations

This repository is an MVP implementation of the architecture
specification.

The following production-oriented capabilities are intentionally not
implemented as full infrastructure:

-   Persistent job database
-   Redis/Celery or distributed task queue
-   Horizontal worker scaling
-   Dedicated GPU worker management
-   Advanced speaker diarization
-   Sophisticated semantic deduplication
-   Production observability/tracing dashboards
-   Authentication and tenant isolation
-   Object storage such as S3
-   Advanced table/layout extraction
-   Fully versioned cache keys
-   Production-grade URL allowlists/network policy
-   Human review workflows

The current job store is in-memory and local artifact/cache storage is
used.

## Manual verification

The implementation was manually verified for the core processing flows,
including:

-   Image processing
-   PDF processing
-   Audio processing
-   Video processing
-   Cache-hit behavior
-   Artifact retrieval
-   Invalid/unsupported input handling
-   Job status/result endpoints
-   LLM-backed topic/summary behavior

An image containing no meaningful text/content correctly produced an
empty extraction rather than fabricated content.

## Design principles

1.  **One pipeline, multiple processors**
2.  **Deterministic extraction first**
3.  **Provenance everywhere**
4.  **Fail gracefully**
5.  **Validate at boundaries**
6.  **Cache safely**
7.  **Do not trust file extensions**
8.  **Keep modality logic isolated**
9.  **Minimize LLM calls**
10. **Return machine-consumable structures**
11. **Version schemas and processing behavior**
12. **Preserve uncertainty instead of inventing information**

## Future production extensions

Potential next-stage improvements include:

-   Object storage
-   Persistent database
-   Redis/Celery task processing
-   GPU-backed workers
-   Horizontal scaling
-   Advanced diarization
-   Better table/layout extraction
-   Content-addressable artifact storage
-   Observability and tracing
-   Authentication and tenant isolation
-   Stronger URL allowlists/network controls
-   Human review for low-confidence extraction

## Project status

**Universal AI Media Processing Pipeline --- MVP implemented and
manually verified.**

The implementation follows the common architecture described in the
project engineering specification and provides a normalized,
provenance-aware output contract across supported media types.
