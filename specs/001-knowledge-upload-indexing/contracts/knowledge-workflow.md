# Knowledge Workflow Contracts

These are internal Python and UI contracts, not network APIs. All names and
types are design targets for implementation, not existing code.

## Upload submission

- Input: a submission of `(filename, bytes)` entries. A processable batch has
  one to ten files, each at most 10 MiB; over-limit inputs still receive the
  specified rejection outcomes.
- An oversized batch is rejected as a whole; each entry is reported as rejected.
- Every submitted entry has a distinct outcome in submission order, including
  same-named entries in an oversized batch. Duplicate filenames within a
  within-limit batch are all rejected; other entries proceed.
- Each rejected file in a within-limit batch reports all applicable duplicate,
  empty-file, unsupported-type, and size validation reasons. Over-limit batches
  are rejected for count before per-file processing.
- Text files must decode as UTF-8. Accept an optional initial byte-order mark,
  remove that initial marker, and reject marker-only files with no document
  text. Reject encrypted PDFs, including those that open without a password.
  Report each rejection with a safe per-file explanation.
- Do not reject an otherwise valid file solely for its content language.
  Documentation states the English retrieval target and does not guarantee
  retrieval quality in other languages.
- Filenames compare exactly, including case and extension. Treat filenames as
  untrusted labels, never as filesystem paths.
- Lifecycle: `pending` -> `validating` -> `processing` -> `indexed` or `failed`;
  validation rejection transitions to `rejected`. Undecodable text, marker-only
  text, and encrypted PDFs are rejected during validation; corrupt parsing,
  no-text PDF extraction, embedding, and storage errors fail during processing.
  Each entered stage is visible.
- A `failed` or `rejected` result contains a safe, actionable error category and
  message, never raw document text, credentials, or internal exception details.
  Errors in one file do not stop the rest of a valid-size batch.
- The upload view is keyboard-operable; each filename is associated with its
  status or error as text accessible to screen readers, without color alone.
- Indexing and replacement become visible to retrieval only after a complete
  commit. A failed replacement leaves the previously committed document intact.

## External processing authorization

- A provider declares whether document text leaves the computer, its identity,
  and the data it receives. A local provider needs no external-service consent.
- For an external provider, show that disclosure and require affirmative consent
  for the specific submission before any document text is sent. Decline or
  absence of consent produces a visible failure without an external call.
- Consent is bound to the selected provider and batch, not persisted for later
  submissions; a new batch or changed provider requires new consent.
- A missing or unavailable configured provider produces a safe failure for
  each affected eligible file, without a silent fallback or partial publication.
- Application-level tests inject a recording external-provider fake and prove
  that no call occurs without consent, including on UI rerun.

## Retrieval

- Input: a question containing at least one non-whitespace character and a
  positive maximum result count. Invalid inputs produce explicit errors.
- Output: ranked list of evidence records containing text, exact source filename,
  chunk identifier, and similarity score. An empty index returns an empty list.
  Otherwise return exactly the lesser of the requested maximum and the number
  of indexed chunks, without filtering by relevance. Candidates do not imply
  that any evidence is sufficient to answer; sufficiency is later-feature scope.
- Scores are cosine similarities: higher scores rank first, with no guaranteed
  order among equal scores. A score is not a calibrated relevance probability.
  Non-finite or zero-magnitude embedding vectors are errors, not similarity scores.
- Search uses the same embedding model and vector representation as the index.
  Reject incompatible model/version/dimension configuration explicitly; never
  silently compare incompatible vectors.
- Provider, validation, and storage failures are explicit errors, not empty
  successful result sets. Callers must treat retrieved text as untrusted data.

## Persistence

- Repository methods provide an atomic replacement of one filename and its
  complete chunk set, and read only committed records. Reads after restart
  preserve both content and provenance.
- An indexing failure before commit leaves previously committed data untouched;
  transaction rollback and restart recovery must not expose partial new chunks.
  After an interruption before commit, the prior version remains available if
  present; after a completed commit, the complete new version remains available.
- Restart persistence assumes the same local knowledge-base location and a
  compatible, available embedding configuration.
- The user keeps the knowledge location local and unshared and is responsible
  for system file sharing and other services; application access restrictions
  do not control those services.
- A documented local cleanup removes all project-owned persistent knowledge data
  and associated metadata after the app is stopped. It does not claim to remove
  data previously sent to an external provider.
