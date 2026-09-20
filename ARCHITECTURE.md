# Architecture

## System flow

```mermaid
flowchart LR
    U[User / API Client]
    API[FastAPI]
    V[Upload Validation]
    S[Document Storage]
    DB[(Relational Database)]
    E[InvoiceExtractor]
    O[AI Provider]
    P[Pydantic Structured Output]
    B[InvoiceBusinessValidator]
    R[Pending Review Queue]
    H[Human Reviewer]
    A[Authoritative Result]
    X[JSON / CSV / API]

    U --> API --> V --> S
    S --> DB
    DB --> E --> O --> P --> B
    B -->|valid| DB
    B -->|review required| R
    R --> H
    H -->|confirm / correct| B
    B -->|human-reviewed pass| DB
    DB --> A
    A -. Milestone 6 .-> X
```

## Milestone 5 review boundary

```text
AI candidate extraction
      ↓
deterministic business validation
      ├── pass   -> document status: validated
      └── issues -> document status: review_required
                        ↓
                  pending Review row
                        ↓
                  human decision
                  ├── confirm as-is
                  └── partial corrections
                        ↓
           deterministic revalidation
                        ├── fail -> review remains pending
                        └── pass -> review completed
                                   document status: reviewed
```

## Candidate vs authoritative record

The original AI extraction is immutable. Human review stores only the fields the reviewer changed.

```text
Extraction row                 Review row
(original AI candidate)        (human correction overlay)
        │                              │
        └──────────────┬───────────────┘
                       ↓
             authoritative result
                       +
              per-field provenance
```

Example:

```text
AI total:      999.00
Human patch:   total = 210.00

original_extraction.total      -> 999.00
corrections.total              -> 210.00
authoritative_result.total     -> 210.00
field_sources.total            -> human
field_sources.vendor_name      -> ai
```

This preserves traceability without duplicating every unchanged field in a second invoice record.

## Responsibility boundaries

| Component | Responsibility |
|---|---|
| Document API | Upload and retrieve safe document metadata |
| Storage service | Sanitize names, validate type, enforce size, persist bytes |
| Extraction API | Coordinate AI extraction, validation, persistence, and initial workflow routing |
| InvoiceExtractor | Call the provider and require strict structured output |
| Extraction Pydantic schema | Define structurally valid invoice data |
| InvoiceBusinessValidator | Apply deterministic arithmetic, required-field, date, currency, and confidence rules |
| Review API | List pending work, show review context, accept human confirmation/corrections |
| Review schema | Constrain partial correction payloads and expose authoritative values with provenance |
| Database | Preserve document metadata, AI candidate data, validation evidence, review audit data, and corrections |

## Why human corrections are revalidated

Human input is more authoritative than AI output, but it is not magically immune to typos. A reviewer could enter a total that still does not reconcile.

Therefore:

```text
human correction
      ↓
same deterministic business rules
      ↓
valid -> complete review
invalid -> HTTP 422, review stays pending
```

The only business check skipped after human review is **AI confidence**. Confidence routed the AI candidate to a person; once a person has reviewed the record, the model's self-reported uncertainty should not block that human decision.

## Review states

```text
pending      review awaits a human decision
completed    a human confirmed/corrected and revalidation passed
superseded   a later clean extraction made the old pending review obsolete
```

Document workflow states now include:

```text
uploaded
  ↓
extracting
  ├── extraction_failed
  ↓
business validation
  ├── validated
  └── review_required
          ↓
       reviewed
```

## Current limitations

- The review is document-level and resolves against the latest extraction rather than storing an explicit `extraction_id` foreign key.
- The correction overlay is exposed through the API; a dedicated review UI is optional later work.
- Schema migrations are not yet managed with Alembic; this portfolio stage uses `create_all` for fresh demo databases.
- Export is Milestone 6.
