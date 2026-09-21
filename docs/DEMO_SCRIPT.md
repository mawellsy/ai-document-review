# Two-Minute Demo Script

## 0:00–0:20 — Business problem

"This project automates invoice data entry while keeping humans in control when AI output is uncertain. The system accepts PDFs or images, extracts structured invoice fields, validates them with deterministic rules, routes exceptions to review, and exports only approved data."

Show the architecture graphic or README workflow.

## 0:20–0:45 — Upload and extraction

Open FastAPI Swagger at `http://127.0.0.1:8000/docs`.

1. Run `POST /documents` with `sample_invoices/invoice_001.png`.
2. Copy the returned document ID.
3. Run `POST /documents/{document_id}/extractions`.

Explain: "The AI must return a strict Pydantic schema. Raw model output is not accepted directly."

## 0:45–1:10 — Deterministic validation

Show `review_required` and `validation_errors` in the extraction response.

For the clean invoice, point out that arithmetic, date, currency, and confidence rules pass.

Then use the inconsistent sample or show `docs/sample_reviewed_result.json`.

Explain: "AI interprets the document, but ordinary Python decides whether the result is trustworthy enough for straight-through processing."

## 1:10–1:35 — Human review and provenance

Open `GET /reviews/{document_id}` for a flagged document, then submit a correction with `POST /reviews/{document_id}`.

Point out:

- the original AI extraction remains unchanged;
- only corrected fields are stored as a human overlay;
- `field_sources` identifies whether each final value came from AI or a reviewer.

## 1:35–1:50 — Authoritative export

Run:

- `GET /documents/{document_id}/result`
- `GET /documents/{document_id}/exports/json`
- or `GET /documents/{document_id}/exports/csv`

Explain: "Pending documents cannot be exported as final data. The API fails closed until the record is validated or reviewed."

## 1:50–2:00 — Reliability proof

Show the test-suite screenshot or run:

```bash
pytest -q
```

Close with:

"The portfolio version demonstrates the same controls I would use in a client automation: validated inputs, typed AI output, deterministic rules, human exception handling, traceability, and tested failure paths."
