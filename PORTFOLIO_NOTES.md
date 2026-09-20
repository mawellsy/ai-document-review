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

## Milestone status

- Milestone 1: complete
- Milestone 2: complete
- Milestone 3: next
