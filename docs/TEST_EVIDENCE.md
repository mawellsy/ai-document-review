# Test Evidence

Milestone 6 baseline test run:

```text
48 passed, 1 warning
```

The warning originates from Starlette's test client dependency and does not represent an application failure.

The suite covers:

- upload validation and safe storage;
- database schema creation;
- strict extraction schemas;
- AI-service retry/failure handling with mocked provider responses;
- deterministic invoice business rules;
- validated vs review-required routing;
- review queue behavior and human corrections;
- authoritative result resolution;
- JSON/CSV export gating;
- health endpoint behavior.

For a fresh verification:

```bash
cd ~/Projects/Upwork/ai-document-review
pytest -q
```
