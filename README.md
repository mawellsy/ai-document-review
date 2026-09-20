# AI Document Extraction & Human Review Pipeline

A portfolio project demonstrating production-style AI document processing with Python, FastAPI, Pydantic, SQLAlchemy, SQLite, structured AI extraction, deterministic business validation, and human-in-the-loop review.

## Business problem

A fictional company manually copies invoice data into internal systems. Manual entry is repetitive, slow, and error-prone. This project automates extraction while preserving human oversight when the AI output is incomplete, low-confidence, or mathematically inconsistent.

## Current scope

**Milestone 4 complete: deterministic business validation**

Implemented so far:

- maintainable Python/FastAPI application structure
- environment-based configuration
- SQLAlchemy database foundation
- `Document`, `Extraction`, `LineItem`, and `Review` models
- synthetic invoice fixtures
- safe PDF/PNG/JPEG upload and local storage
- UUID-based document identity
- upload size and file-signature validation
- `POST /documents`, `GET /documents/{id}`, and `GET /documents`
- strict Pydantic schema for AI invoice output
- OpenAI Responses API adapter for image and PDF inputs
- structured-output parsing instead of manual JSON parsing
- configurable retry limit for provider/structured-output failures
- persisted extraction metadata and line items
- deterministic invoice business validation
- configurable confidence and monetary tolerance thresholds
- ISO 4217 currency-code checking
- structured validation errors persisted with each extraction
- automatic `validated` vs `review_required` routing state
- mocked AI tests with no live API calls
- portfolio and learning notes

Not implemented yet:

- human review endpoints and correction workflow
- authoritative corrected-record handling
- export

Those remain separate milestones so the review workflow can build on already-persisted validation evidence rather than mixing extraction, validation, and correction into one oversized route.

## Architecture

```mermaid
flowchart TD
    A[API Client] --> B[POST /documents]
    B --> C[Upload Validation]
    C --> D[UUID File Storage]
    D --> E[(Document Metadata)]
    E --> F[POST /documents/id/extractions]
    F --> G[InvoiceExtractor]
    G --> H[AI Provider]
    H --> I[Strict Pydantic Schema]
    I --> J[InvoiceBusinessValidator]
    J -->|PASS| K[validated]
    J -->|REVIEW| L[review_required]
    K --> M[(Extraction + Line Items)]
    L --> M
    L -. Milestone 5 .-> N[Human Review Queue]
```

### Trust boundary

```text
untrusted document
      ↓
upload validation
      ↓
stored document
      ↓
probabilistic AI extraction
      ↓
strict Pydantic structure validation
      ↓
deterministic business validation
      ├── pass   -> validated
      └── issues -> review_required
```

The model interprets the document. Python defines whether the resulting candidate data is acceptable for automatic processing.

## Repository structure

```text
ai-document-review-pipeline/
├── app/
│   ├── api/
│   │   ├── documents.py
│   │   └── extractions.py
│   ├── core/
│   │   └── config.py
│   ├── db/
│   ├── models/
│   ├── schemas/
│   │   ├── document.py
│   │   └── extraction.py
│   ├── services/
│   │   ├── storage.py
│   │   ├── extraction.py
│   │   └── validation.py
│   └── main.py
├── sample_invoices/
├── scripts/
├── storage/uploads/
├── tests/
├── .env.example
├── ARCHITECTURE.md
├── LEARNING_NOTES.md
├── PORTFOLIO_NOTES.md
├── pyproject.toml
├── requirements.txt
└── README.md
```

## API workflow

### 1. Upload an invoice

```bash
curl -X POST \
  -F "file=@sample_invoices/invoice_001.png" \
  http://127.0.0.1:8000/documents
```

### 2. Extract and validate invoice data

```bash
curl -X POST \
  http://127.0.0.1:8000/documents/<DOCUMENT_ID>/extractions
```

The endpoint now performs two different kinds of validation:

1. **Structural validation:** Pydantic checks types, dates, allowed fields, numeric ranges, and line-item shape.
2. **Business validation:** ordinary Python checks whether the structurally valid data makes business sense.

A successful extraction therefore does **not** automatically mean the invoice is trusted.

### 3. Read the latest extraction

```bash
curl \
  http://127.0.0.1:8000/documents/<DOCUMENT_ID>/extractions/latest
```

The response includes:

```json
{
  "review_required": false,
  "validation_errors": []
}
```

An inconsistent invoice can instead return:

```json
{
  "review_required": true,
  "validation_errors": [
    {
      "code": "invoice_total_mismatch",
      "field": "total",
      "message": "Subtotal plus tax does not approximately equal total.",
      "observed": "999.00",
      "expected": "210.00"
    }
  ]
}
```

The original AI extraction remains persisted even when review is required. Milestone 5 will let a human correct it without destroying the original candidate data.

## Business validation rules

`InvoiceBusinessValidator` currently checks:

- required auto-accept fields are present;
- at least one line item exists;
- currency is an assigned transactional ISO 4217 code;
- AI confidence meets `AI_CONFIDENCE_THRESHOLD`;
- due date is not earlier than invoice date;
- `subtotal + tax` approximately equals `total`;
- each line item's `quantity × unit_price` approximately equals its `amount`;
- line-item amounts approximately sum to `subtotal`.

Money comparisons use decimal arithmetic and a configurable tolerance instead of exact floating-point equality.

## Processing states

```text
uploaded
   ↓
extracting
   ├── provider/schema failure -> extraction_failed
   ↓
AI candidate extracted
   ↓
business validation
   ├── no issues -> validated
   └── issues    -> review_required
```

Milestone 5 will turn `review_required` into an actual human review queue and correction workflow.

## Configuration

Copy the example file:

```bash
cp .env.example .env
```

Configure as needed:

```text
DATABASE_URL=sqlite:///./document_review.db
UPLOAD_DIR=storage/uploads
MAX_UPLOAD_MB=10
AI_PROVIDER=openai
AI_MODEL=<document-capable-model>
AI_API_KEY=<your-api-key>
AI_MAX_ATTEMPTS=2
AI_CONFIDENCE_THRESHOLD=0.80
AMOUNT_TOLERANCE=0.01
```

Never commit `.env` or a real API key.

## Local setup

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.init_db
uvicorn app.main:app --reload
```

Interactive documentation:

```text
http://127.0.0.1:8000/docs
```

## Tests

```bash
pytest -q
```

Milestone 4 adds tests for:

- clean invoices passing validation;
- missing required fields;
- invalid ISO currency codes;
- low AI confidence;
- invoice-total mismatches;
- line-item subtotal mismatches;
- line-item quantity/price mismatches;
- invalid invoice/due-date chronology;
- monetary tolerance behavior;
- API persistence of validation errors;
- automatic `validated` and `review_required` status transitions.

The suite still uses mocked AI responses, so automated tests do not call a live provider.

## Milestone boundary

Milestone 4 answers:

> Is the AI-extracted candidate internally consistent enough to accept automatically, and if not, can the system explain exactly why it needs review?

Milestone 5 will answer:

> Can a human review and correct flagged documents while preserving the original AI extraction and a traceable correction record?
