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

1. **Given** a supported non-empty text or PDF file with extractable text,
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
   restarted in the same configured environment, **Then** its chunks remain
   retrievable with their source metadata.
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
    rejected, and no files are processed.
13. **Given** a batch of at most 10 files containing a file larger than 10 MiB,
    **When** it is submitted, **Then** that file is rejected with a clear
    explanation and the other files are processed independently.
14. **Given** indexed knowledge is stored locally, **When** the user follows
    the documented removal procedure, **Then** the local knowledge base is
    removed and its content is no longer retrievable.
15. **Given** the application is running on the user's computer, **When** a
    remote computer attempts to access the upload view or knowledge base,
    **Then** access is denied.

### Edge Cases

- An empty, corrupt, encrypted, or image-only PDF that yields no extractable text
  fails clearly rather than being marked as indexed.
- A file with an allowed extension but unreadable or incompatible content fails
  processing with a safe explanation.
- If two files with the same filename are submitted in one batch, both are
  rejected with an explanation so that replacement order is not ambiguous.
- A failed indexing attempt must not leave partial new chunks available for
  retrieval or remove a previously indexed version.
- A batch within the file-count limit may contain both valid and invalid files;
  each receives an independent final outcome.
- Files of exactly 10 MiB and batches of exactly 10 files meet the size and
  count limits; files or batches above those limits are rejected as specified.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow one or more files to be submitted through a
  knowledge-upload view and MUST accept `.txt` and `.pdf` files. Support for
  `.md` files is desirable but not required.
- **FR-002**: The system MUST display each submitted filename and its processing
  status, including a final success or failure outcome.
- **FR-003**: The system MUST reject empty files and unsupported file types
  with a per-file explanation.
- **FR-004**: The system MUST parse accepted content, divide extractable text
  into chunks, create embeddings, and store the resulting knowledge for later
  retrieval.
- **FR-005**: Each indexed chunk MUST retain its source filename and a chunk
  identifier sufficient to distinguish it within that document.
- **FR-006**: The system MUST expose retrievable evidence for a relevant question,
  including the content and source metadata, without requiring a question-answering
  UI.
- **FR-007**: The system MUST report validation, parsing, embedding, and storage
  failures for the affected file and MUST NOT label failed processing as success.
  Messages MUST NOT expose credentials, sensitive document content, or internal
  implementation details.
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
  application is restarted in the same configured environment.
- **FR-013**: The application MUST restrict access to the knowledge-upload view
  and knowledge base to the local computer; remote access is not supported.
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
- **SC-003**: For at least one known question against an indexed sample, the
  returned evidence includes the expected fact and correct source identifiers.
- **SC-004**: In replacement checks, a successful same-name upload replaces the
  previous contents, and a failed replacement leaves the previous contents
  retrievable without exposing partial new contents.
- **SC-005**: In a manual walkthrough, a user can identify the status and final
  outcome of every file in a mixed batch without inspecting internal logs.

## Assumptions

- A filename match means the complete displayed filename matches exactly,
  including case and extension. Files with different names are separate documents.
- A PDF must contain extractable text; extracting text from images is not required.
- The configured knowledge base is for one user on their own computer;
  authentication and per-user access control are outside this feature.
- Embedding and storage capabilities are available in the configured environment.
  Their specific providers and capacity limits are planning decisions.
- Questions and example documents used for verification contain no private or
  inaccessible copyrighted material.

## Verification

- Automated checks cover valid, empty, unsupported, corrupt, and unprocessable
  files; chunk creation and source metadata; known-evidence retrieval; mixed
  batches; replacement success and failure; persistence across restart; and
  upload count and size boundaries. Check local-only access, external-service
  disclosure and per-batch opt-in, and documented knowledge-base removal.
- Use deterministic embedding and storage substitutes where appropriate so
  routine tests do not require live providers. Verify persistence behavior using
  a suitable local test environment.
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
