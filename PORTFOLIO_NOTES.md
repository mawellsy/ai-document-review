# Portfolio Notes

## Problems solved

- Manual invoice data entry is repetitive and error-prone.
- Raw AI extraction is not trustworthy enough to become business data without validation.
- Uncertain documents need a controlled path to human review rather than silent failure.
- AI and human changes need traceability.
- Uploaded files must be accepted without allowing client-controlled filenames or malformed content to dictate server storage behavior.

## Skills demonstrated so far

- Python project structure
- FastAPI application and routing
- multipart file uploads
- dependency injection
- environment-based configuration
- SQLAlchemy 2.x ORM modeling and sessions
- relational database design
- safe local file persistence
- UUID-based identifiers
- MIME/extension/signature validation
- streaming size enforcement
- HTTP error handling
- synthetic test-data design
- isolated API tests with temporary database/filesystem state
- security-conscious secret and upload handling

## Architectural decisions

### SQLite first

Use SQLite for local development and the portfolio demo. Keep ORM code database-agnostic enough to migrate to PostgreSQL later.

Why: zero infrastructure for the demo, while still demonstrating SQL and relational modeling.

### Separate Document, Extraction, Review, and LineItem entities

Why: clear audit trail, queryable data, and separation between uploaded source, AI interpretation, human correction, and repeated invoice rows.

### Separate HTTP routes from storage logic

`app/api/documents.py` owns HTTP behavior. `app/services/storage.py` owns file validation and persistence.

Why: the storage rules can be tested and changed without turning API route functions into unmaintainable piles of unrelated logic.

### Server-generated stored filenames

Preserve a sanitized original filename only for metadata. Store the physical file under a UUID-derived filename.

Why: avoids filename collisions and prevents client-controlled path strings from becoming server paths.

### Validate actual bytes

Do not rely solely on extension or MIME header. Detect PDF/PNG/JPEG using signature bytes and require extension/content consistency.

Why: request metadata is supplied by the client and can be wrong or malicious.

### Stream rather than buffer full files

Read and write uploads in chunks while counting bytes.

Why: the configured size limit is enforced without memory usage scaling directly with upload size.

### Compensate for database failure

If the file reaches storage but the database insert fails, remove the file.

Why: prevents orphaned storage objects and demonstrates thinking beyond the happy path.

### Preserve raw AI response

Why: debugging and auditability. The application can show what the model originally returned if validation or review later changes the final record.

### Deterministic validation outside the LLM

Why: arithmetic, required fields, dates, and allowed currency codes are ordinary software rules. They should not be delegated to probabilistic text generation.

## Measurable business benefits to quantify later

- estimated minutes saved per invoice
- reduction in manual keying steps
- percentage of documents accepted automatically
- percentage routed to review
- average correction time
- extraction/validation error rate in demo dataset
- invalid uploads rejected before incurring AI API cost

## Demo moments to capture later

1. open `/docs` and upload the synthetic invoice
2. show `201 Created` with UUID document metadata
3. retrieve the same document through `GET /documents/{id}`
4. attempt an invalid upload and show controlled rejection
5. show extracted structured JSON
6. show a valid invoice passing automatically
7. show a bad total entering the review queue
8. correct the record manually
9. retrieve/export the authoritative result
10. run tests showing failure-path coverage

## Potential Upwork proposal talking points

- "I validate uploads before paying for AI processing, including format, content signature, and size limits."
- "I separate storage, API, AI extraction, and business validation so each layer is independently testable."
- "I build AI workflows with deterministic validation rather than blindly trusting model output."
- "The workflow keeps the original extraction and human correction for traceability."
- "The architecture starts simple with SQLite but is structured for a PostgreSQL deployment."
- "I include failure-path tests and human review for low-confidence cases."

## Milestone 3 additions

### Skills demonstrated

- multimodal/document-capable AI API integration
- strict Pydantic structured output
- provider adapter/service boundaries
- base64 image and PDF request construction
- configurable retry behavior
- persistence of AI candidate data and line items
- processing-status transitions
- mocking an external AI provider in unit/API tests
- separating probabilistic extraction from deterministic validation

### Architectural decisions

#### Require typed structured output

The extraction service requests a Pydantic-defined result rather than asking the model for loose JSON and manually decoding it later.

Why: application code receives a validated object with known fields and types. Unexpected keys, malformed dates, invalid confidence ranges, and malformed line items fail before persistence.

#### Keep business validation out of the extraction service

Milestone 3 verifies structure. Milestone 4 verifies invoice truth conditions such as arithmetic and allowed currency codes.

Why: "valid JSON" and "valid business record" are different claims and should have different tests and failure handling.

#### Mock the AI provider in automated tests

Tests inject a fake client/extractor instead of calling a live model.

Why: tests remain deterministic, fast, offline, and free of API charges. Live-provider smoke tests can be separate and opt-in later.

#### Record the model used

Every extraction persists `model_used` and the structured candidate response.

Why: model versions can change output behavior. Recording the model improves debugging and auditability.

### Demo moments added

- upload `invoice_001.png`;
- call `POST /documents/{id}/extractions`;
- show typed invoice JSON returned and persisted;
- retrieve it through `/extractions/latest`;
- demonstrate a mocked provider failure test and `extraction_failed` status;
- point out that arithmetic validation is handled by a separate deterministic service.

## Milestone 4 additions

### Problems solved

- structurally valid AI output can still contain mathematically inconsistent invoice data;
- low-confidence results now route to review instead of being treated as trusted;
- invalid currency codes and suspicious date ordering are detected deterministically;
- every review-required extraction now carries machine-readable reasons.

### Skills demonstrated

- deterministic post-AI validation
- financial arithmetic with `Decimal` and configurable tolerance
- ISO 4217 currency validation
- configurable confidence-based routing
- structured error design
- workflow state modeling
- integration of validation results with persistence and API responses
- unit and API testing for business-rule failure paths

### Architectural decisions

#### Validate after structured extraction

The AI first produces data that satisfies the Pydantic contract. `InvoiceBusinessValidator` then checks business invariants.

Why: malformed data and inconsistent data are different failure classes and should remain independently testable.

#### Preserve failed candidates

A review-required extraction is still persisted with its original AI values plus structured validation errors.

Why: reviewers need to see what the AI produced, and the project needs an audit trail before human corrections become authoritative in Milestone 5.

#### Route instead of discard

Business-rule failures set `review_required=true` and the document status to `review_required` rather than deleting or silently rewriting the extraction.

Why: uncertain documents still contain useful work and should be recoverable by a person.

### Demo moments added

- process the valid synthetic invoice and show `review_required=false`;
- process an inconsistent invoice and show `invoice_total_mismatch`;
- show the document status changing to `validated` or `review_required`;
- point out `observed` and `expected` values in the validation error;
- run the business-validation tests to demonstrate deterministic failure handling.

## Milestone status

- Milestone 1: complete
- Milestone 2: complete
- Milestone 3: complete
- Milestone 4: complete
- Milestone 5: next

## Milestone 5 additions

### Problems solved

- flagged invoices now enter an actual human work queue instead of stopping at a status flag;
- reviewers can see why a document needs attention before changing anything;
- human corrections become authoritative without overwriting the original AI extraction;
- low-confidence but otherwise correct invoices can be explicitly confirmed by a person;
- invalid human edits are rejected before a review is completed;
- field-level provenance distinguishes AI-derived values from human-corrected values.

### Skills demonstrated

- human-in-the-loop workflow design
- review queue API design
- partial update/overlay semantics
- immutable candidate records and authoritative read models
- data provenance and auditability
- workflow-state transitions
- deterministic validation of human edits
- SQLAlchemy relationship loading and persisted review audit fields
- integration tests covering multi-step business workflows

### Architectural decisions

#### Preserve the AI extraction

The `Extraction` row remains unchanged after review. Human edits are stored in `Review.corrected_values_json`.

Why: replacing AI values would destroy evidence needed to explain what the model originally produced and what the reviewer actually changed.

#### Compute an authoritative read model

The review detail endpoint merges the immutable AI candidate with the persisted human correction overlay and returns `field_sources` for every business field.

Why: downstream consumers need one usable record, while auditors need provenance. The merge gives both without copying unchanged values.

#### Revalidate human corrections

A review cannot complete while corrected values still violate deterministic invoice rules. AI-confidence routing is skipped after a human decision.

Why: human authority should override model uncertainty, but not arithmetic, currency, required-field, or chronology rules.

#### Support confirm-as-is

An empty correction object is a valid human decision.

Why: some documents are routed to review only because confidence is low; a reviewer should be able to confirm correct values without inventing a fake edit.

### Demo moments added

- create an inconsistent extraction and show it appearing in `GET /reviews`;
- open `GET /reviews/{document_id}` and show the AI values plus review reason;
- correct only `total` through `POST /reviews/{document_id}`;
- show that `original_extraction.total` stays wrong while `authoritative_result.total` is corrected;
- show `field_sources.total = human` and unchanged fields remaining `ai`;
- demonstrate a bad correction returning `422` and leaving the review pending;
- show the document state changing from `review_required` to `reviewed`.

## Milestone status

- Milestone 1: complete
- Milestone 2: complete
- Milestone 3: complete
- Milestone 4: complete
- Milestone 5: complete
- Milestone 6: next
