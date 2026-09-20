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
