# Agentic RAG Knowledge Assistant

A local Python application for uploading knowledge files, indexing them with
FastEmbed, and retrieving ranked evidence with source provenance. Feature 001
does not generate answers; retrieval candidates are not a guarantee of
relevance or sufficient evidence.

## Setup and launch

Requirements: Python 3.11-3.13 and `uv`.

```powershell
uv sync --locked
.\run.ps1
```

`run.ps1` starts Streamlit on `127.0.0.1`. The application refuses an unset or
non-loopback effective bind address. Keep Streamlit's security protections
enabled. Loopback binding is not authentication against other local processes;
keep the knowledge directory on an unshared local location.

Settings are read from environment variables; the application does not
automatically load a `.env` file. See [.env.example](.env.example) for supported
names. The default database is `data/knowledge/knowledge.sqlite3`, and the local
embedding model cache is separate at `data/model-cache`.

The first indexing or retrieval operation may download the configured
`BAAI/bge-small-en-v1.5` model files. This download does not send document text.
To operate offline, prepare the model cache beforehand. A missing model or
failed download is reported; the application does not silently switch models.
Documents are limited to UTF-8 text and text-extractable, unencrypted PDFs.
Retrieval targets English; quality for other languages is not guaranteed.

## Upload and retrieval

Submit files from the Streamlit form. Each submitted file receives an
independent textual status; application checks enforce a maximum of 10 files
and 10 MiB per file, regardless of client-side widget behavior. Documents and
vectors are stored together in SQLite and become visible only after a complete
transactional commit. Replacing a failed document preserves its previous
committed version.

To inspect ranked evidence and provenance from a terminal:

```powershell
uv run --locked python -m app.retrieval_check --help
uv run --locked python -m app.retrieval_check "Where is the observatory?"
```

The command prints JSON evidence records containing text, filename, chunk ID,
and cosine score. Scores are not calibrated relevance probabilities. The
default offline test suite uses deterministic substitutes and does not
download a model or contact Langfuse.

## Trace privacy and permissions

Tracing is optional. Configure `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, and
`LANGFUSE_SECRET_KEY` only when needed; never commit real credentials. With no
host configured, the application reports tracing as unavailable and indexing
continues.

The UI displays the destination and exported field categories before enabling
trace export. External export remains disabled until explicitly authorized and
can be revoked. A loopback Langfuse destination instead requires an explicit,
process-lifetime confirmation and an application-verified direct loopback
connection. Confirmation is required again after application restart and can
be invalidated when routing changes. Local confirmation does not establish that
the receiving service will not forward data; the user is responsible for that
service's configuration. Trace payloads exclude document text, questions,
filenames, paths, vectors, credentials, and raw exceptions.

Indexing uses the local embedding model and has no external indexing provider
configured. Indexing authorization is distinct from trace-export permission.
The application cannot recall data already delivered to a trace destination.

## Checks

```powershell
uv run --locked ruff check app tests
uv run --locked ruff format --check app tests
uv run --locked pyright
uv run --locked pytest
```

The real-model check is opt-in and requires a preloaded model cache:

```powershell
$env:RUN_REAL_MODEL_TESTS = "1"
uv run --locked pytest tests\integration\test_real_model.py
```

Use temporary, non-sensitive data for manual verification. AppTest cannot
establish browser transport-limit behavior, keyboard operation in the rendered
browser, or screen-reader behavior; follow the manual checks in
[the feature quickstart](specs/001-knowledge-upload-indexing/quickstart.md).

## Removing local knowledge

Stop the Streamlit application first. The default knowledge database and its
SQLite journal files and reservation metadata are project-owned persistent
knowledge data. The following commands remove only those named paths; if
`KNOWLEDGE_DIR` is customized, use that configured directory instead.

PowerShell:

```powershell
$database = ".\data\knowledge\knowledge.sqlite3"
Remove-Item -LiteralPath $database, "${database}-journal", "${database}-wal", "${database}-shm" -Force -ErrorAction SilentlyContinue
$reservations = "${database}.reservations"
if (Test-Path -LiteralPath $reservations) {
    Remove-Item -LiteralPath $reservations -Recurse -Force
}
```

Linux:

```sh
rm -f -- data/knowledge/knowledge.sqlite3 \
  data/knowledge/knowledge.sqlite3-journal \
  data/knowledge/knowledge.sqlite3-wal \
  data/knowledge/knowledge.sqlite3-shm
rm -rf -- data/knowledge/knowledge.sqlite3.reservations
```

These commands do not remove backups, copies made by other software, or data
already sent to an external provider, and they do not guarantee secure erasure.
The separate model cache contains model files, not uploaded documents.
