# Data Model: Knowledge Upload and Indexing

## KnowledgeDocument

| Field | Rule |
|-------|------|
| `document_id` | Internal stable identifier for a committed document. |
| `filename` | Required exact-case filename; unique using binary comparison. |
| `indexed_at` | Time of last successful commit. |
| `embedding_model_id` | Model and resolved revision/file identity; must match the index. |
| `embedding_dimension` | Positive dimension; must match all associated vectors. |

One document owns one or more chunks. Replacements retain no old chunks after
commit. Filename is a label, not a path or an authority for filesystem access.

## KnowledgeChunk

| Field | Rule |
|-------|------|
| `document_id` | Required foreign key to a committed document. |
| `chunk_id` | Identifier unique within the document, derived from ordered position. |
| `text` | Non-empty extracted content. |
| `embedding` | Finite float32 values matching the configured model dimension. |
| `page` | Optional source PDF page number when available. |

Use a unique `(document_id, chunk_id)` key. Enable SQLite foreign-key
enforcement on every connection. Store vectors in the same transactional
database as their text and metadata.

## UploadBatch and UploadResult

These are transient session/application values, not persistent document records.
An upload batch contains at most 10 files; an over-limit submission is rejected
as a whole. A result includes filename, status, and a safe message. Status
transitions are specified in [knowledge-workflow.md](contracts/knowledge-workflow.md).
Consent for a remote provider is tied to one batch and provider and is not
stored as standing permission.

## Consistency and lifecycle

- Parse, chunk, and embed a candidate fully before opening the replacement write
  transaction. Invalid input or provider failures leave committed data unchanged.
- In one transaction delete or replace the old document and chunks and write the
  complete candidate; commit once. Roll back on any write error. Queries read
  committed records only, including after process restart.
- The database records the embedding identity and dimension for the whole index.
  Refuse reads or writes on a mismatch and require a deliberate rebuild; do not
  silently mix embeddings from different models or revisions.
- Chunk boundaries must fit the selected model's token limit, including special
  tokens, without silently truncating document text. Overlap must not leave
  gaps in the extracted text.
- Keep uploaded bytes in memory for processing only. Store chunk text and vectors
  in the configured local knowledge directory, not the original uploaded file.
  The model cache is separate and must not contain document text.
- Removal guidance identifies all local database files and related journal/WAL
  files and requires stopping the app before removal. It does not claim secure
  erasure, removal of backups, or deletion at an external provider.
