# Feature Specification: Knowledge Upload and Indexing

**Feature Branch**: `001-knowledge-upload-indexing`

**Created**: 2026-11-22

**Status**: Draft

**Input**: Upload one or more knowledge files, display per-file indexing status, and
make their contents retrievable with source metadata.

## Clarifications

### Session 2026-11-22

- Q: Who is allowed to access the knowledge base in the first release? → A: One user on their own computer; no remote access.
- Q: May uploaded document content be sent to an external service to make it searchable? → A: Only after clear disclosure and explicit user opt-in.
- Q: What upload limits should the first release enforce? → A: At most 10 files per batch, each at most 10 MiB.
- Q: How long should permission to send document text to an external indexing service last? → A: Ask for each upload batch that uses an external service.
- Q: How should the user remove indexed knowledge from the first release? → A: Document how to remove the entire local knowledge base outside the application.
- Q: How should the application protect the local knowledge base from access through file sharing or other services? → A: Use an unshared local location; the user is responsible for system sharing and other services.
- Q: What accessibility requirements should apply to upload statuses and errors? → A: Require text labels, keyboard access, and screen-reader access for status and errors.
- Q: Within a permitted-size batch, what should a file's rejection message say when it violates multiple rules? → A: Report all applicable validation reasons for each rejected file.
- Q: Which text-file encodings should the application accept? → A: Accept UTF-8 text files only; clearly reject files that cannot be decoded.
- Q: What language support should the indexed knowledge base promise? → A: Target English; other languages may be uploaded, but retrieval quality is not guaranteed.
- Q: How should the application handle encrypted PDF files? → A: Reject all encrypted PDFs, including those that open without a password.
- Q: What should retrieval return when the knowledge base contains documents but none appear relevant to the question? → A: Return the highest-ranked chunks without claiming relevance; the later answer workflow judges sufficiency.
- Q: How should a UTF-8 text file with an initial byte-order mark be handled? → A: Accept UTF-8 with or without an initial marker and remove that initial marker before indexing.
- Q: What final status should be shown for undecodable text and encrypted PDFs? → A: Mark both as rejected; mark parsing, embedding, and storage errors as failed.
- Q: How should retrieval handle a question containing only whitespace? → A: Reject empty or whitespace-only questions with an explicit input error.
- Q: What should happen when two submissions try to index the same filename at the same time? → A: Reject the later same-name attempt while the first is in progress, with a clear message to retry.
- Q: Where may workflow traces be sent? → A: Use a local or external Langfuse destination; external export requires separate explicit opt-in.
- Q: How long should permission to send sanitized traces to an external observability service last? → A: Until explicitly revoked or the destination changes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload and Index Knowledge (Priority: P1)

As a user, I want to upload one or more knowledge files and see their indexing
status, so their contents can later be used to answer my questions.

**Why this priority**: Indexed knowledge is the foundation for evidence-based
answers; users need to know whether each upload is usable.

**Independent Test**: Upload known non-empty text and PDF documents, observe each
status, and verify that a known question retrieves relevant source-identified
content without using a question-answering interface.

**Acceptance Scenarios**:

1. **Given** a supported non-empty UTF-8 text file or unencrypted PDF with
   extractable text,
   **When** the user submits it for indexing, **Then** its name and progress are
   displayed, its content is indexed as retrievable chunks with source metadata,
   and a success message is shown only after indexing completes.
2. **Given** a batch within the file-count limit, **When** multiple files are
   submitted together, **Then** each has its own status and final outcome, and
   failure of one does not prevent other valid files from being processed.
3. **Given** an empty file or unsupported file type, **When** it is submitted,
   **Then** the file is rejected with a clear per-file explanation and is not
   reported as indexed.
4. **Given** a supported file that cannot be parsed, contains no extractable text,
   or cannot be embedded or stored, **When** processing fails, **Then** the user
   sees a clear per-file failure and the file is not reported as successfully
   indexed.
5. **Given** an indexed document containing a known fact, **When** retrieval is
   checked with a relevant question, **Then** relevant evidence is returned
   with its source filename and chunk identifier.
6. **Given** an indexed document and a new file with the same filename,
   **When** the new file is successfully indexed, **Then** it replaces the old
   document and its chunks in the knowledge base.
7. **Given** an indexed document and a new file with the same filename,
   **When** validation or indexing of the new file fails, **Then** the previous
   document remains retrievable and the replacement failure is shown.
8. **Given** a batch containing two files with the same filename, **When** the
   batch is submitted, **Then** both files are rejected with an explanation and
   any previously indexed document of that name remains unchanged.
9. **Given** a successfully indexed document, **When** the application is
   restarted using the same local knowledge-base location and compatible
   embedding configuration, **Then** its chunks remain retrievable with their
   source metadata.
10. **Given** indexing would send document text to an external service,
    **When** the user has not explicitly opted in after being told what data
    and service are involved, **Then** no document text is sent and the user
    receives a clear explanation.
11. **Given** indexing would send document text to an external service and the
    user has explicitly opted in after disclosure, **When** the user submits a
    supported file, **Then** indexing may use that service for that batch only;
    another batch requires a new opt-in.
12. **Given** a batch of more than 10 files, **When** it is submitted, **Then**
    the batch is rejected with a clear explanation, each file is shown as
    rejected in submission order, including separately shown same-named entries,
    and no files are processed.
13. **Given** a batch of at most 10 files containing a file larger than 10 MiB,
    **When** it is submitted, **Then** that file is rejected with a clear
    explanation and the other files are processed independently.
14. **Given** indexed knowledge is stored locally, **When** the user follows
    the documented removal procedure, **Then** the local knowledge base is
    removed and its content is no longer retrievable.
15. **Given** the application is running on the user's computer, **When** a
    remote computer attempts to access the upload view or knowledge base
    through the application, **Then** access is denied.
16. **Given** per-file statuses or errors are available, **When** a user
    operates the upload view with a keyboard and screen reader, **Then** each
    filename and its status or error are available as text, without relying
    on color alone.
17. **Given** indexing is interrupted, **When** the application restarts,
    **Then** an interruption before a document is fully committed leaves no
    partial new chunks retrievable and preserves any previously committed
    version. If the complete new version was committed before interruption,
    that version remains retrievable instead.
18. **Given** a batch within the file-count limit contains a file violating
    multiple validation rules, **When** the batch is submitted, **Then** that
    file is rejected with all applicable validation reasons and other valid
    files receive independent outcomes.
19. **Given** a `.txt` file that cannot be decoded as UTF-8, **When** it is
    submitted, **Then** it is marked rejected, is not indexed, and the user
    sees a clear per-file explanation.
20. **Given** a user consults the setup documentation, **When** they review
    language support, **Then** it states the English target and that retrieval
    quality in other languages is not guaranteed.
    **Given** an otherwise valid file in another language, **When** it is
    submitted, **Then** its language alone does not cause rejection.
21. **Given** an encrypted PDF, including one that opens without a password,
    **When** it is submitted, **Then** it is marked rejected, is not indexed,
    and the user sees a clear per-file explanation.
22. **Given** an indexed knowledge base and a valid unrelated question,
    **When** evidence is requested, **Then** the highest-ranked available
    chunks are returned without a claim that they are relevant or sufficient.
23. **Given** a UTF-8 text file with an initial byte-order mark and non-empty
    content, **When** it is indexed, **Then** the initial marker is removed and
    its remaining content is available as evidence.
24. **Given** an empty or whitespace-only question, **When** evidence is
    requested, **Then** retrieval reports an explicit input error rather than
    returning a successful empty result.
25. **Given** the configured embedding provider is missing or unavailable,
    **When** eligible files are submitted for indexing, **Then** each affected
    file is marked failed with a safe explanation, no replacement is published,
    and the system does not silently substitute another provider.
26. **Given** a non-positive retrieval result limit, **When** evidence is
    requested, **Then** retrieval reports an explicit input error.
27. **Given** a file is already being indexed, **When** another submission
    attempts to index the same exact filename in the same knowledge base,
    **Then** the later file is rejected with a clear retry message, other
    eligible files in its batch proceed independently, and no existing
    committed version is changed by the rejected attempt.
    **When** the first attempt finishes or is interrupted, **Then** a later
    submission can retry that filename.
28. **Given** an eligible file cannot acquire its filename reservation because
    of an unexpected error, **When** validation finishes, **Then** its status
    changes from validating to failed with a safe explanation, no processing
    or replacement occurs, and other eligible files proceed independently.
29. **Given** a configured, available trace destination, **When** indexing or
    retrieval completes or fails, **Then** its trace records the entered
    workflow steps, their outcomes and durations, and available model and usage
    details without recording sensitive content.
30. **Given** an external trace destination, **When** external trace export has
    not been explicitly enabled for that destination, **Then** no trace data is
    sent to it. Permission remains in effect until revoked or the destination
    changes; a changed destination requires a new opt-in.
31. **Given** tracing is unavailable or a tracing failure is detected,
    **When** indexing or retrieval proceeds, **Then** a safe observability
    warning is reported without changing the operation's actual outcome or
    hiding an application failure.

### Edge Cases

- An encrypted PDF fails clearly even if it opens without a password. An empty,
  corrupt, or image-only PDF that yields no extractable text also fails clearly
  rather than being marked as indexed.
- A file with an allowed extension but unreadable or incompatible content fails
  processing with a safe explanation.
- A `.txt` file that cannot be decoded as UTF-8 fails with a clear per-file
  explanation rather than silently changing or discarding its content.
- A UTF-8 file containing only an initial byte-order mark has no document text
  and fails rather than being marked as indexed.
- If two files with the same filename are submitted in one batch, both are
  rejected with an explanation so that replacement order is not ambiguous.
- Overlapping submissions to the same knowledge base cannot index the same
  exact filename simultaneously, even if they originate from separate sessions
  or application processes. A rejected overlap does not alter committed data.
- An unexpected reservation error fails the affected file before processing;
  it does not permit unprotected indexing or modify committed knowledge.
- Trace creation or delivery can fail independently of indexing or retrieval;
  a detected observability failure is reported separately from the operation.
- A failed indexing attempt must not leave partial new chunks available for
  retrieval or remove a previously indexed version.
- An interruption before commit leaves the previous committed document, if
  any, available after restart; an interruption after commit leaves the
  complete new version available, never a partial version.
- A batch within the file-count limit may contain both valid and invalid files;
  each receives an independent final outcome.
- Within the file-count limit, a file can violate multiple validation rules;
  its rejection explains each applicable violation. An oversized batch is
  rejected for its count before per-file processing.
- Files of exactly 10 MiB and batches of exactly 10 files meet the size and
  count limits; files or batches above those limits are rejected as specified.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow one or more files to be submitted through a
  knowledge-upload view and MUST accept UTF-8 `.txt` files and unencrypted
  `.pdf` files with extractable text. Support for `.md` files is desirable but
  not required.
- **FR-002**: The system MUST display each submitted filename and its processing
  status, including a final success or failure outcome. Outcomes MUST retain
  submission order and distinguish separate entries, even when filenames match
  or the batch exceeds the file-count limit.
- **FR-003**: The system MUST reject empty files and unsupported file types
  with a per-file explanation.
- **FR-004**: The system MUST parse accepted content, divide extractable text
  into chunks, create embeddings, and store the resulting knowledge for later
  retrieval.
- **FR-005**: Each indexed chunk MUST retain its source filename and a chunk
  identifier sufficient to distinguish it within that document.
- **FR-006**: The system MUST expose retrievable evidence for a relevant question,
  including the content and source metadata, without requiring a question-answering
  UI. For a valid question and a positive result limit, retrieval returns the
  lesser of that limit and the number of indexed chunks, ranked without a
  relevance threshold; these candidates do not assert that the evidence is
  relevant or sufficient.
  An empty index returns no candidates. Empty or whitespace-only questions
  and non-positive limits MUST produce an explicit input error. Evidence
  sufficiency and abstention belong to the later answer workflow.
- **FR-007**: The system MUST report validation, parsing, embedding, and storage
  failures for the affected file and MUST NOT label failed processing as success.
  Messages MUST NOT expose credentials, sensitive document content, or internal
  implementation details. Undecodable text and encrypted PDFs MUST be marked
  rejected; corrupt parsing, no-text PDF extraction, embedding, and storage
  errors MUST be marked failed.
  If the configured embedding provider is missing or unavailable, affected
  eligible files MUST be marked failed with a safe explanation, without silently
  substituting another provider or publishing partial results.
- **FR-008**: Each file in a batch within the file-count limit MUST be processed
  independently; an error for one file MUST NOT prevent other valid files from
  reaching their own final outcome.
- **FR-009**: A successful upload with the same filename as an indexed document
  MUST replace that document's indexed contents and source metadata. A failed
  replacement MUST leave the previously indexed version available.
- **FR-010**: The system MUST prevent partially indexed content from a failed
  upload or replacement from appearing in retrieval results.
- **FR-011**: The system MUST reject all same-named files submitted together in
  a single batch with a clear explanation.
- **FR-012**: Successfully indexed content MUST remain retrievable after the
  application is restarted with the same local knowledge-base location and a
  compatible embedding configuration, provided those dependencies are available.
- **FR-013**: The application MUST restrict access to the knowledge-upload view
  and knowledge base through the application to the local computer; remote
  application access is not supported. The user MUST use an unshared local
  location for knowledge files and is responsible for system sharing and other
  services that could expose those files.
- **FR-014**: Before document text is sent to an external indexing service, the
  user MUST be told which service receives which data and MUST explicitly opt in.
  Opt-in applies to one upload batch only and MUST be requested again for each
  later batch using an external service. Without opt-in, the system MUST NOT send
  the text and MUST explain why indexing cannot proceed using that service.
- **FR-015**: The system MUST reject a batch containing more than 10 files before
  processing any file and show each file as rejected. For a batch of at most 10
  files, it MUST reject each file larger than 10 MiB (10,485,760 bytes) while
  processing the other files independently. Rejections MUST explain the
  applicable limit.
- **FR-016**: Documentation MUST provide a procedure to remove the entire local
  knowledge base outside the application, including its indexed content and
  associated metadata.
- **FR-017**: The upload view MUST be operable by keyboard. Each filename and
  its status or error MUST be available to screen readers as associated text;
  conveying an outcome MUST NOT rely on color alone.
- **FR-018**: For a batch within the file-count limit, a rejected file MUST
  report all applicable duplicate-name, empty-file, unsupported-type, and
  file-size validation reasons. An over-limit batch MUST be rejected for its
  file count before per-file processing.
- **FR-019**: An interruption before a document is fully committed MUST leave
  no partial new chunks retrievable after restart and MUST preserve any
  previously committed version. A completed commit MUST leave the complete
  new version retrievable after restart.
- **FR-020**: The system MUST reject a `.txt` file that cannot be decoded as
  UTF-8 with a clear per-file explanation and MUST NOT silently alter or discard
  undecodable content. A UTF-8 file may contain an initial byte-order mark;
  the system MUST remove that initial marker before indexing while retaining
  the remaining text, and reject a marker-only file as having no document text.
- **FR-021**: Documentation MUST state that retrieval targets English and that
  quality in other languages is not guaranteed. The system MUST NOT reject an
  otherwise valid file solely because its content is in another language.
- **FR-022**: The system MUST reject encrypted PDFs, including those that open
  without a password, with a clear per-file explanation.
- **FR-023**: For a knowledge base, the system MUST allow at most one indexing
  attempt for an exact filename to proceed at a time across sessions and
  application processes. After batch and per-file validation, it MUST reject a
  conflicting attempt with a safe message to retry, without changing committed
  knowledge or blocking other eligible filenames in the batch. When attempts
  reach this point concurrently, the first to reserve the filename proceeds;
  submission order is not guaranteed.
  The filename becomes available for retry when the active attempt completes,
  fails, or is interrupted. Same-batch duplicate and other validation rules
  continue to apply.
- **FR-024**: An unexpected filename-reservation error MUST transition the
  affected file from validating to failed with a safe per-file explanation.
  The system MUST NOT process that file or change its committed knowledge;
  other eligible files MUST continue independently. A conflicting reservation
  remains a rejection under FR-023, not an unexpected reservation error.
- **FR-025**: When tracing is available, the system MUST trace each submitted
  file, including entries rejected for batch count, and each retrieval request.
  Indexing traces MUST identify entered validation, reservation, parsing,
  chunking, embedding, and storage steps; retrieval traces MUST identify entered
  input-validation, query-embedding, and evidence lookup and ranking steps.
  Each entered step and its parent operation MUST include an outcome and
  non-negative elapsed duration; record embedding model identity and usage
  details when available, without inventing unavailable values. A rejected or
  failed operation MUST record only steps actually entered.
- **FR-026**: Traces and observability diagnostics MUST exclude document bytes
  and text, questions, filenames, file paths, embedding vectors, credentials,
  and raw exception details. Use non-content operation identifiers, controlled
  step names, safe error categories, sanitized model identities, and numeric
  usage details for correlation and diagnosis. External trace export MUST be
  disabled unless the user explicitly opts in for the selected destination
  after disclosure of its identity and the data sent. This permission is
  separate from indexing consent, persists until revoked, and is invalidated
  when the destination changes.
  The user MUST be able to revoke it. Export authorization MUST be checked at
  dispatch; discard unsent queued traces after revocation or a destination
  change. Previously transmitted data cannot be recalled. Local trace
  destinations do not require external-export consent.
- **FR-027**: Missing or unavailable trace configuration and detected trace
  creation or delivery failures MUST produce a safe observability warning,
  separately from the indexing or retrieval outcome. Upload warnings MUST be
  visible in the upload view; retrieval callers MUST be able to access a safe
  diagnostic through a separate operation-correlated channel without changing
  the evidence result shape. Observability failures MUST NOT prevent core
  operations, alter their outcomes, or hide their errors.
  The system MUST NOT claim successful delivery without confirmation.

### Key Entities *(include if feature involves data)*

- **Knowledge document**: An uploaded file identified by its filename, with an
  indexing outcome and a collection of indexed chunks.
- **Knowledge chunk**: A portion of extracted document content, associated with
  a source filename and chunk identifier for retrieval and later citation.
- **Upload result**: The per-file processing status and final success or failure
  message associated with a submission.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a verification set containing at least one valid text file and
  one valid PDF, 100% of the files are indexed successfully and each produces
  retrievable chunks with source filename and chunk identifier.
- **SC-002**: In a mixed-file verification batch, 100% of empty, unsupported,
  and deliberately unprocessable files are reported as failures, while each
  valid file reaches a separate successful outcome.
- **SC-003**: For the known-evidence example in Verification, returned evidence
  includes the specified fact, exact source filename, and the identifier of
  the indexed chunk containing that fact.
- **SC-004**: In replacement checks, a successful same-name upload replaces the
  previous contents, and a failed replacement leaves the previous contents
  retrievable without exposing partial new contents.
- **SC-005**: In a manual walkthrough, a user can identify the status and final
  outcome of every file in a mixed batch without inspecting internal logs.
- **SC-006**: In offline checks with a recording trace substitute, every
  exercised indexing and retrieval operation includes exactly the entered
  required steps, their outcomes and durations, and available model or usage
  details; no prohibited sensitive values appear in recorded trace data.

## Assumptions

- A filename match means the complete displayed filename matches exactly,
  including case and extension. Files with different names are separate documents.
- A PDF must be unencrypted and contain extractable text; extracting text from
  images is not required.
- Retrieval targets English; accepting another language does not guarantee its
  retrieval quality.
- The configured knowledge base is for one user on their own computer;
  authentication and per-user access control are outside this feature.
- The user controls the operating system and other services and keeps the
  knowledge-base location local and unshared. Application access restrictions
  do not control file sharing or access through those services.
- Embedding and storage capabilities are available in the configured environment.
  Their specific providers and capacity limits are planning decisions.
- Questions and example documents used for verification contain no private or
  inaccessible copyrighted material.

## Verification

- Automated checks cover valid, empty, unsupported, corrupt, and unprocessable
  files, including `.txt` files that are not decodable as UTF-8 and encrypted
  PDFs with and without a required password; chunk creation and source metadata;
  known-evidence retrieval; mixed
  batches; replacement success, failure, and interruption before and after
  commit; persistence across restart; and
  upload count and size boundaries. Check local-only access, external-service
  disclosure and per-batch opt-in, documented knowledge-base removal, and
  keyboard and screen-reader access to per-file statuses and errors. Cover
  files with overlapping validation violations and over-limit batch precedence.
  Check the documented language expectation and acceptance of otherwise valid
  files regardless of content language. Check empty-index and unrelated-question
  retrieval without treating returned candidates as proof of relevance. Cover
  empty and whitespace-only questions, non-positive result limits, a missing
  provider, duplicate entries in oversized batches, and UTF-8 files with and
  without an initial marker and marker-only files. Exercise overlapping
  same-name submissions across sessions and processes, independently
  progressing other filenames, preservation of committed evidence, and retry
  after completion, failure, and interruption. Inject an unexpected reservation
  error and check the validating-to-failed transition and unchanged knowledge.
- Use deterministic embedding and storage substitutes where appropriate so
  routine tests do not require live providers. Verify persistence behavior using
  a suitable local test environment.
- With a recording trace substitute, check successful, rejected, and failed
  indexing and successful and failed retrieval: operation and entered-step
  names, outcomes, non-negative durations, parent relationships, available model
  and usage metadata, and the absence of document text, questions, filenames,
  paths, vectors, credentials, and raw exception details. Use recognizable
  sentinel values for prohibited inputs and injected errors. Check external
  export is blocked before opt-in and after revocation or a destination change,
  including for traces awaiting dispatch,
  while local destinations do not require that opt-in. Inject trace creation
  and delivery failures and verify safe warnings and unchanged core outcomes,
  including simultaneous application failure. Routine checks require no live
  observability service.
- Known-evidence example: index an original text file named `observatory.txt`
  containing only `The observatory is located in Larch Valley.` Ask `Where is
  the observatory located?` The returned evidence must contain that sentence,
  identify `observatory.txt`, and identify its indexed chunk. This is a minimum
  acceptance example, not a claim about retrieval quality on other questions.
- Manual walkthrough: start the application; submit a valid text file, a valid
  PDF, an empty file, and an unsupported file; observe each filename and outcome;
  then repeat an upload with the same filename and verify the replacement outcome.
  Use the available retrieval check to verify a known fact and its source.
  Follow the documented removal procedure on test data and verify it is no longer
  retrievable.

## Out of Scope

- A user-facing question-answering interface, answer generation, citation
  rendering, and hallucination guardrails.
- CrewAI answer orchestration and end-to-end question-answer Langfuse traces.
- Evaluation dataset creation, generated evaluation report, and final submission.
- Authentication, user account management, and per-user authorization.
- In-app removal of individual indexed documents.
