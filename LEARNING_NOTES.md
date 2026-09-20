# Learning Notes

These are the concepts you should be able to explain without reading the code line-by-line.

## 1. FastAPI routes and dependency injection

A route maps an HTTP request to Python logic.

```text
HTTP request -> route -> service/database -> response
```

Milestone 2 uses FastAPI dependencies for two things:

- `get_db()` provides one SQLAlchemy session per request.
- `get_settings()` provides configuration such as upload directory and size limit.

Why dependency injection matters: tests can replace these dependencies with a temporary database and temporary upload directory. Production code does not need test-specific branches.

## 2. POST vs GET

`POST /documents` creates a new server-side resource, so a successful request returns `201 Created`.

`GET /documents/{id}` reads one resource and should not modify it.

`GET /documents` reads a collection.

Pattern:

```text
POST = create/change server state
GET  = retrieve server state
```

## 3. Multipart file uploads

Browser/API file uploads commonly use `multipart/form-data`.

A FastAPI `UploadFile` gives the application:

- a client-supplied filename;
- a client-supplied MIME type;
- a file-like stream containing bytes.

The first two are claims from the client, not trusted facts.

## 4. MIME type vs file signature

A MIME type is metadata such as:

```text
image/png
application/pdf
```

A file signature, sometimes called magic bytes, is a recognizable byte prefix inside the file itself.

Examples used by the project:

```text
PDF  -> %PDF-
PNG  -> 89 50 4E 47 0D 0A 1A 0A
JPEG -> FF D8 FF
```

The storage service checks actual bytes, then compares them with the extension and submitted MIME type.

This does not make uploads perfectly safe. It does make validation materially stronger than trusting the filename alone.

## 5. Why uploaded filenames cannot be trusted

A client could submit a name resembling:

```text
../../private/config.txt
```

If an application naïvely joins that string to its storage directory, `..` path segments can attempt to escape the intended directory. This is called path traversal.

This project does two things:

1. keeps only the basename for human-readable metadata;
2. never uses that basename as the actual stored filename.

The stored path is based on a server-generated UUID.

## 6. UUIDs

A UUID is a large identifier designed to be unique without a central sequence generator.

For uploaded documents it gives us:

```text
Document.id      = 8b...<uuid>
stored filename  = 8b...<uuid>.png
```

Benefits:

- avoids collisions between two users uploading `invoice.pdf`;
- does not expose an incrementing record number;
- decouples storage identity from client-controlled filenames.

## 7. Streaming and upload-size limits

A dangerous implementation does this:

```text
read entire 100 MB file into memory -> then check size
```

The project instead processes chunks:

```text
read chunk -> count bytes -> write chunk
    ^               |
    |               +-> stop if limit exceeded
    +------------------- repeat
```

This keeps memory use roughly bounded by chunk size rather than file size.

If the limit is exceeded, the partial stored file is deleted.

## 8. Database session lifecycle

Each request gets its own SQLAlchemy `Session`.

```text
request starts
    ↓
open DB session
    ↓
query / write
    ↓
commit or rollback
    ↓
close session
```

A session tracks database work as a unit. `commit()` makes successful writes durable. `rollback()` abandons the failed transaction.

## 9. Filesystem + database consistency

The filesystem and SQLite are separate systems. One transaction cannot automatically commit both.

Possible failure:

```text
file save succeeds
DB insert fails
```

Without cleanup, the system has an orphan file.

Milestone 2 compensates by deleting the stored file if database persistence fails.

This is not a distributed transaction. It is a simple compensating action appropriate to the current architecture.

## 10. Pydantic response schemas

The SQLAlchemy `Document` model represents persistence.

The Pydantic `DocumentResponse` schema represents what the API exposes.

Keeping them separate matters because the database contains internal fields such as `storage_path` and `stored_filename`. Clients do not need those implementation details.

```text
Database model -> response schema -> API client
```

## 11. Test isolation

Milestone 2 tests use:

- an in-memory SQLite database;
- a temporary filesystem directory;
- FastAPI dependency overrides.

This means tests do not modify the developer's real `document_review.db` or `storage/uploads` directory.

A good automated test should be repeatable regardless of what files happened to be left from yesterday's debugging expedition.

## 12. HTTP failure codes used here

```text
201 Created             upload accepted
404 Not Found           document ID does not exist
413 Content Too Large   configured size limit exceeded
415 Unsupported Media   file format/content rejected
500 Server Error        persistence unexpectedly failed
```

The important idea is that expected client errors are not reported as generic `500` failures.

## Study before Milestone 3

Be comfortable explaining:

- request/response Pydantic schemas
- deterministic parsing vs probabilistic extraction
- structured LLM output
- why raw LLM JSON cannot be trusted directly
- retryable vs non-retryable AI failures
- mocking external APIs in tests
- why model name and raw response should be recorded for auditability

# Milestone 3 concepts

## 13. Probabilistic extraction vs deterministic validation

An LLM is probabilistic: the same conceptual task can produce different outputs, and a plausible output can still be wrong.

Pydantic validation is deterministic: the same input is checked against the same explicit rules every time.

```text
invoice image
    ↓
LLM interpretation        probabilistic
    ↓
Pydantic schema           deterministic structure check
    ↓
Milestone 4 rules         deterministic business check
```

The LLM should do the work that requires interpretation. Ordinary software should enforce rules that can be stated exactly.

## 14. Structured output

Structured output means the model is constrained to return data matching a defined schema rather than free-form prose.

For this project the schema is `InvoiceExtractionPayload`.

Benefits:

- predictable keys;
- typed dates and numbers;
- bounded confidence value;
- rejection of unexpected fields;
- less manual JSON parsing code;
- easier persistence and testing.

Important limitation: schema validity does not prove factual correctness. A model can return a valid `total: 210.00` even if the invoice visibly says `201.00`.

## 15. Pydantic `extra="forbid"`

By default, silently accepting unexpected model fields can hide provider drift or prompt mistakes.

`extra="forbid"` means:

```text
expected schema + unexpected key -> validation failure
```

That is useful at an AI boundary because the application should notice when the provider returns data outside the agreed contract.

## 16. Why images and PDFs use different provider inputs

A PNG/JPEG is sent as an image input.

```text
bytes -> base64 -> data:image/... -> input_image
```

A PDF is sent as a file input.

```text
bytes -> base64 -> data:application/pdf -> input_file
```

The service hides those provider-specific details from the route.

## 17. Service adapter pattern

`InvoiceExtractor` acts as an adapter between application concepts and the provider SDK.

```text
Application concept: "extract this invoice"
                ↓
InvoiceExtractor
                ↓
Provider-specific request/response API
```

The route does not need to know how base64 inputs, `responses.parse`, or provider response objects work.

This reduces coupling and makes mocking straightforward.

## 18. Retryable failures

External APIs fail for reasons your code does not control:

- temporary network problems;
- transient provider errors;
- malformed/invalid structured output.

A small retry count can recover from transient failures.

```text
attempt 1 -> failure
attempt 2 -> success
```

But configuration mistakes such as a missing API key are not transient. Retrying the same missing credential merely performs the same failure with admirable persistence and no useful result.

The current project uses a simple maximum-attempt policy. More advanced production systems may add exponential backoff and error-specific retry rules.

## 19. Why AI calls are mocked in tests

A unit test should answer whether *our code* behaves correctly.

Calling a live model introduces unrelated variables:

- network availability;
- provider uptime;
- API cost;
- model updates;
- nondeterministic output.

So tests inject fake provider responses:

```text
fake failure -> fake success
```

and verify that our retry logic behaves correctly.

A separate optional integration/smoke test can later verify real provider connectivity without making the core test suite unreliable.

## 20. Processing status as workflow state

The document status now moves through states such as:

```text
uploaded -> extracting -> extracted
                      \
                       -> extraction_failed
```

This is a small state machine. The status tells other parts of the system what has happened and what actions are valid next.

Later milestones will add states related to validation and review.

## Study before Milestone 4

Be able to explain:

- the difference between structural validation and business validation;
- why `subtotal + tax ≈ total` belongs in Python rather than the prompt;
- decimal/tolerance issues in monetary comparisons;
- how confidence thresholds should route work rather than prove correctness;
- why validation errors should be stored as structured data;
- how a document transitions from extracted candidate data to accepted or review-required data.

## 21. Milestone 4: structural validity is not business validity

A Pydantic model can prove that `total` is a non-negative number. It cannot prove that the number is correct for the invoice.

```text
Structural question: Is total a valid numeric field?
Business question: Does subtotal + tax approximately equal total?
```

Keeping those questions separate is a reusable design pattern for AI systems. The model handles interpretation; deterministic code handles rules that can be stated exactly.

## 22. Why business validation should be deterministic

Rules such as arithmetic reconciliation, required fields, known currency codes, and date ordering have exact answers. Asking an LLM to decide them would make a deterministic problem probabilistic.

The preferred flow is:

```text
AI proposes candidate data
        ↓
Python checks invariants
        ↓
pass or human review
```

An invariant is a condition that should remain true for acceptable data. Here, one invariant is `subtotal + tax ≈ total`.

## 23. Decimal arithmetic and tolerance

Binary floating-point numbers cannot exactly represent many decimal fractions. Financial comparisons therefore should not rely on expressions like:

```python
0.1 + 0.2 == 0.3
```

The validator converts extracted values to `Decimal` and uses a configurable tolerance:

```text
abs(expected - observed) <= 0.01
```

The tolerance represents the maximum harmless difference caused by rounding. It is a business parameter, not a mathematical universal.

## 24. Confidence is a routing signal, not proof

An AI confidence score does not prove correctness. A high-confidence extraction can still be wrong, and a low-confidence one can be right.

The useful role of confidence is operational:

```text
confidence >= threshold -> eligible for auto-acceptance
confidence < threshold  -> human review
```

It is one signal among several deterministic checks.

## 25. Why validation failures use codes

A structured issue such as:

```json
{
  "code": "invoice_total_mismatch",
  "field": "total",
  "observed": "250.00",
  "expected": "210.00"
}
```

can be counted, filtered, displayed in a review UI, or analyzed later. A single free-form string is harder for software to use reliably.

Stable machine-readable codes and human-readable messages serve different consumers.

## 26. Workflow state means business state

Milestone 4 distinguishes three important outcomes:

```text
validated         = extraction succeeded and deterministic checks passed
review_required   = extraction succeeded but one or more checks failed
extraction_failed = no acceptable structured extraction was produced
```

This distinction matters operationally. A review-required invoice is useful data awaiting a human decision; an extraction failure may need a retry, provider investigation, or manual entry.

## Study before Milestone 5

Be able to explain:

- why original AI values must remain immutable after human correction;
- the difference between a candidate record and an authoritative record;
- why review reasons should be shown to the reviewer;
- how audit fields such as reviewer, corrected time, and original values support traceability;
- why a review endpoint should validate human corrections too.
