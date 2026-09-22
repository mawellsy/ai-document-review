# Test Evidence

Phase 2 Milestone 8 verification:

```text
52 passed
```

The suite covers:

- upload validation and safe storage;
- ORM database schema creation;
- Alembic upgrade/downgrade behavior;
- PostgreSQL production-configuration guardrails;
- SQLite foreign-key enforcement used by local/tests;
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
cd ai-document-review
pytest -q
```

The portfolio screenshot in `docs/screenshots/test-suite.png` captures the completed Phase 1 suite; the text evidence above tracks the current Phase 2 test count.
