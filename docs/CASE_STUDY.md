# Case Study: AI Document Extraction & Human Review Pipeline

## Problem

A fictional operations team receives invoices as PDFs and images. Employees manually read each invoice and key fields such as invoice number, vendor, dates, totals, currency, and line items into internal systems.

The manual workflow has three recurring problems:

1. repetitive data entry consumes staff time;
2. transcription mistakes can become downstream accounting errors;
3. a fully automated AI-only workflow would be risky because model output can be incomplete, low-confidence, or mathematically inconsistent.

## Solution

This project implements a production-style document-processing pipeline with five trust layers:

1. **Upload validation** verifies allowed formats, signature bytes, size limits, and safe storage names.
2. **AI extraction** converts invoice images/PDFs into a strict Pydantic schema.
3. **Deterministic business validation** checks arithmetic, required fields, dates, currency codes, line items, and AI confidence.
4. **Human review** preserves the original AI candidate while allowing a reviewer to confirm or correct flagged fields.
5. **Authoritative export** exposes only validated or reviewed records through API, JSON, or CSV.

The system deliberately separates probabilistic interpretation from deterministic business rules. AI reads the document. Python decides whether the candidate can be trusted automatically.

## Architecture

See [`docs/architecture.svg`](architecture.svg) and [`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Reliability choices

- raw AI output is never trusted directly;
- strict schema validation occurs before persistence;
- review-required documents are routed rather than discarded;
- original AI values remain immutable after human correction;
- final exports fail closed while a document is unresolved;
- tests mock the AI provider, so the test suite is deterministic and does not spend API credits;
- upload validation occurs before AI processing, avoiding unnecessary provider cost for invalid files.

## Business value

For a representative workflow, assume manual invoice entry takes **4 minutes per document** and validated straight-through processing requires **30 seconds of staff attention on average** for exceptions and spot checks.

| Monthly invoices | Manual effort | Automated human effort | Approx. time saved |
| ---: | ---: | ---: | ---: |
| 250 | 16.7 hours | 2.1 hours | 14.6 hours |
| 1,000 | 66.7 hours | 8.3 hours | 58.4 hours |
| 5,000 | 333.3 hours | 41.7 hours | 291.6 hours |

These figures are a **demonstration model, not measured production results**. Real savings depend on invoice complexity, review rate, provider latency, and the client's existing workflow.

## Skills demonstrated

- Python backend engineering
- FastAPI REST API design
- Pydantic structured outputs
- SQLAlchemy relational modeling
- SQLite with a PostgreSQL-ready ORM boundary
- multimodal/document AI integration
- deterministic post-AI validation
- human-in-the-loop workflow design
- audit trails and field-level provenance
- JSON/CSV export
- file-upload security controls
- failure-path testing with pytest
- modular service boundaries and configuration management

## Demo outcome

A portfolio demo can show the full workflow in under three minutes:

1. upload a synthetic invoice;
2. extract typed invoice data;
3. show a clean invoice passing automatically;
4. show an inconsistent invoice entering review;
5. correct one field without overwriting the AI record;
6. export the authoritative result;
7. show the passing automated test suite.

## Limitations

- SQLite is appropriate for the local demo but PostgreSQL would be preferable for multi-user production deployment.
- Local filesystem storage should be replaced with object storage such as S3 for distributed deployment.
- Authentication and role-based access control are not implemented in this portfolio version.
- Review is API-driven rather than using a dedicated review dashboard.
- Database migrations are not managed with Alembic yet.
- The portfolio test suite mocks the AI provider; a production deployment should add a small opt-in live-provider smoke test.

## Natural next improvements

- PostgreSQL + Alembic migrations
- S3-compatible document storage
- authentication and reviewer roles
- lightweight review dashboard
- webhook notification on processing completion
- batch upload/export
- metrics for automatic-accept rate, review rate, correction rate, latency, and AI cost per document
