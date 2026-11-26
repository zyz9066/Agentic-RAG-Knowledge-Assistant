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
| `embedding` | Finite float32 values matching the configured model dimension, with nonzero vector magnitude. |
| `page` | Optional source PDF page number when available. |

Use a unique `(document_id, chunk_id)` key. Enable SQLite foreign-key
enforcement on every connection. Store vectors in the same transactional
database as their text and metadata.

## UploadBatch and UploadResult

These are transient session/application values, not persistent document records.
The submitted batch snapshots widget-accepted entries at explicit submit; files
rejected by the widget before submission have no application result. An
over-limit submission is rejected as a whole. Each submitted entry has a fresh,
opaque, non-content operation identifier assigned before batch validation.
A result associates that identifier with the entry's filename, status, and safe
message; a trace, when available, uses the same identifier. Separate entries
remain distinguishable even with matching filenames. Status
transitions are specified in [knowledge-workflow.md](contracts/knowledge-workflow.md).
Consent for a remote provider is tied to one batch and provider and is not
stored as standing permission.

## Trace export permission

External trace permission is separate from upload-batch consent. It is an
explicit, persistent opt-in bound to the selected destination; revocation or
any destination change invalidates it. Store no credentials in the permission
record. Invalidation coordinates with dispatch start; discard unsent queued
traces, while already-started dispatches may finish and delivered data cannot
be recalled. Local-exemption confirmation is a separate process-lifetime value
bound to the destination, not persistent across restart. It records the user's
attestation of the local receiving service and delivery path; local dispatch
also requires direct loopback and peer verification, bypassing configured
proxies and not following redirects. Missing confirmation or unverifiable
application checks make the destination external. Coordinate revocation and
known destination or routing changes across sessions and processes using the
destination, preventing new dispatch and discarding unsent queued traces under
invalidated confirmations. The app cannot independently verify downstream
forwarding by the receiving service.

## Retrieval operation

The caller obtains a fresh opaque operation identifier before invoking retrieval
and passes it with the request. A separate diagnostic channel associates safe
warnings with that identifier, including on failure. The evidence list and its
records do not include it. Concurrent invocations use distinct identifiers.

## Consistency and lifecycle

- Parse, chunk, and embed a candidate fully before opening the replacement write
  transaction. Invalid input or provider failures leave committed data unchanged.
- After validation, reserve the exact filename per knowledge base before
  processing; coordinate threads, sessions, and application processes. Reject
  overlapping attempts with a retry message, without blocking other filenames.
  Hold the reservation until completion or failure and release it on process
  interruption, so retries are not permanently blocked. Reservation errors
  must not permit unprotected indexing.
- In one transaction delete or replace the old document and chunks and write the
  complete candidate; commit once. Roll back on any write error. Queries read
  committed records only, including after process restart.
- The database records the embedding identity and dimension for the whole index.
  Refuse reads or writes on a mismatch and require a deliberate rebuild; do not
  silently mix embeddings from different models or revisions.
- Reject non-finite or zero-magnitude query and chunk vectors rather than
  producing undefined cosine similarity.
- Chunk boundaries must fit the selected model's token limit, including special
  tokens, without silently truncating document text. Overlap must not leave
  gaps in the extracted text.
- Keep uploaded bytes in memory for processing only. Store chunk text and vectors
  in the configured local knowledge directory, not the original uploaded file.
  The model cache is separate and must not contain document text.
- Removal guidance identifies all local database files and related journal/WAL
  files and requires stopping the app before removal. It does not claim secure
  erasure, removal of backups, or deletion at an external provider.
