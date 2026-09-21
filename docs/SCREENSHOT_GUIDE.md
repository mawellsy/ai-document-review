# Screenshot Guide

Ready-to-use visuals are stored in `docs/screenshots/`:

- `architecture.png` — end-to-end system architecture;
- `sample-invoice.png` — synthetic invoice input used in the demo;
- `test-suite.png` — automated test verification.

For an Upwork portfolio gallery, add two live screenshots after configuring a test API key:

1. **Review-required extraction** showing a structured validation issue such as `invoice_total_mismatch` and `review_required: true`.
2. **Authoritative reviewed result** showing `result_source: human_reviewed` and `field_sources` with at least one human-corrected field.

Keep screenshots tightly cropped around the evidence that matters. Do not show API keys, `.env`, secrets, or irrelevant terminal history.
