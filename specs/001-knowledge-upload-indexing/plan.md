# Implementation Plan: Knowledge Upload and Indexing

**Branch**: `001-knowledge-upload-indexing` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-knowledge-upload-indexing/spec.md`

## Summary

Build a local-only Streamlit upload view backed by a small Python ingestion
pipeline. Parse text and PDF, chunk extracted text, embed locally with FastEmbed,
and persist chunk text, provenance, and vectors together in SQLite. Rank stored
vectors by cosine similarity through a small retrieval interface. Commit each
document replacement in one SQLite transaction so a failed upload cannot hide
or partially replace previously indexed knowledge.

## Technical Context

**Language/Version**: Python 3.11 minimum; target 3.11-3.13 on Windows and Linux
in CI. Declare the actual tested range in `pyproject.toml`.

**Primary Dependencies**: Streamlit 1.67.0, pypdf 7.1.1, FastEmbed 0.9.1;
pytest, Ruff, and Pyright for development. Resolve compatible transitive
dependencies and record exact versions in `uv.lock` during implementation.
Separate binary-only dependency resolutions succeeded for Python 3.11-3.13 on
Windows and Linux; a unified lock and platform/runtime verification remain to be
performed.

**Storage**: One local SQLite database containing document metadata, chunk text,
and float32 embedding vectors. Use exact cosine search over committed vectors;
no separate vector service or native SQLite extension.

**Testing**: pytest unit/integration tests; Streamlit AppTest where supported,
with a browser/manual upload check for behavior it cannot simulate; deterministic
embedding fakes; a real SQLite database in temporary directories.

**Target Platform**: Local single-user Windows and Linux development environments;
bind the supported launch to loopback only.

**Project Type**: Local Python modular-monolith application.

**Performance Goals**: No latency target was specified. Show per-file progress
and outcomes; measure indexing and retrieval performance on the sample corpus.

**Constraints**: At most 10 files per batch, each at most 10 MiB; `.txt` and
text-extractable `.pdf` required; no document text sent externally without
per-batch disclosure and opt-in. Failure must not publish partial data.

**Scale/Scope**: One local user and a small knowledge base. Exact vector scanning
is intentionally not a large-corpus solution; no throughput guarantee is made.

## Constitution Check

| Principle | Pre-research | Post-design |
|-----------|--------------|-------------|
| Grounding and provenance | Pass: preserve source and chunk identity. | Pass: evidence contract returns source and chunk metadata; answer generation is later work. |
| Security and privacy | Pass: local-only access, validation, safe errors. | Pass: loopback launch, local embeddings, per-batch consent boundary, no raw content in logs. |
| Modular Python architecture | Pass: small monolith and clear boundaries. | Pass: separate upload, retrieval, persistence, embedding, UI, and configuration responsibilities. |
| Verifiable quality | Pass: deterministic tests and real persistence checks. | Pass: focused offline tests, optional real-model smoke, lint and type-check gates. |
| Observable, reliable workflows | Pass: explicit statuses and failures for ingestion. | Pass: sanitized diagnostic events and per-file status; CrewAI/Langfuse question traces remain Feature 2 scope. |
| Technology and workflow | Pass: Python, Streamlit, reproducible lock, Spec Kit. | Pass: plan and contracts precede implementation; `uv.lock`, Ruff, Pyright, and CI planned. |

No constitution exception is required. The actual unified dependency lock, CI
matrix, and runtime behavior must be validated during implementation; resolution
checks do not prove that packages were installed or ran successfully.

## Project Structure

### Documentation (this feature)

```text
specs/001-knowledge-upload-indexing/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── knowledge-workflow.md
└── tasks.md             # future /speckit-tasks output
```

### Source Code (repository root)

```text
app/
├── ui.py                # Streamlit form, consent, statuses
├── config.py            # validated settings and local paths
├── ingestion.py         # validation, parsing, chunking, coordination
├── embeddings.py        # local embedding adapter and protocol
├── retrieval.py         # evidence retrieval interface
├── retrieval_check.py   # local verification CLI, not an answer UI
└── storage.py           # SQLite transactions and exact vector search
data/sample-knowledge/   # public-domain or original sample fixtures
tests/
├── unit/
└── integration/
```

**Structure Decision**: One application package with explicit responsibilities.
The local retrieval interface can be reused by Feature 2 without exposing a
network service or coupling core logic to Streamlit. Create the listed files
only during implementation.

## Design and Verification

1. Use a Streamlit form to snapshot a batch and explicit submit action. Keep
   status in session state across reruns, avoid repeating a submission on rerun,
   and update visible per-file statuses. Validate count, size, extension, content,
   and duplicate names server-side; never trust the widget filter alone. Report
   all applicable per-file validation reasons within a permitted-size batch;
   reject an oversized batch for count before per-file processing. Make the
   upload view keyboard-operable and associate each filename with textual
   status and error information accessible to screen readers without relying
   on color alone.
2. Read UTF-8 text and extract PDF text with pypdf. Reject undecodable text and
   empty, unreadable, corrupt, encrypted, and no-text inputs explicitly;
   reject encrypted PDFs even if no password is required. Split with overlap
   using the embedding model's tokenizer and token limit, including special tokens;
   never silently truncate content during embedding. Retain document-relative
   order and optional PDF page numbers.
3. Default to the local FastEmbed `BAAI/bge-small-en-v1.5` model. A first-use
   model download may require network access, but document text must not be sent
   for that download. Explain the download and cache; fail explicitly if model
   files are unavailable. Document the English retrieval target without promising
   multilingual retrieval quality; do not reject otherwise valid files solely
   because their content is in another language.
4. Compute all new chunks and vectors before opening a short SQLite write
   transaction. In the transaction, replace a filename's document and all
   chunks together, then commit. Roll back on failure. Validate vector
   dimensions and embedding identity, and reject incompatible index/model
   combinations instead of returning misleading results.
5. Implement local embedding now. Define a provider capability contract for
   external processing and test consent with a recording fake; a production
   remote embedding integration is not required in Feature 001. If one is later
   added, the disclosure and per-batch opt-in gate applies before any transfer.
6. Bind the supported Streamlit launch explicitly to `127.0.0.1`; check effective
   server configuration and fail closed on non-loopback binding. Keep Streamlit
   security protections enabled and display sanitized errors. Loopback is not
   authentication against other local processes; the single-user trust
   assumption remains explicit. Document that the user must keep knowledge
   files in an unshared local location and is responsible for other services
   and system file sharing.
7. Test validation boundaries, undecodable text, encrypted PDFs with and without
   a required password, supported formats, corrupt/no-text PDFs, mixed batches,
   acceptance of otherwise valid non-English content, overlapping validation
   reasons, duplicate names, progress,
   accessibility, consent, safe messages, atomic rollback, interruption before
   and after commit, restart persistence, local-only access, and the specified
   known-evidence retrieval example. Include
   an opt-in real-model test on the sample corpus; deterministic fakes alone do
   not establish real semantic retrieval quality.
8. Document setup, model download and offline limitations, `.env.example` with
   variable names only if external credentials are introduced later, local data
   removal, manual checks, and operational errors. Never commit secrets, local
   knowledge databases, uploaded files, model caches, or sensitive test data.

## Complexity Tracking

No constitution violations or exceptions.
