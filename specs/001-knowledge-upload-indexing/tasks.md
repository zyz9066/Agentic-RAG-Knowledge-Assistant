---

description: "Implementation tasks for knowledge upload and indexing"
---

# Tasks: Knowledge Upload and Indexing

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [knowledge-workflow.md](contracts/knowledge-workflow.md),
and [quickstart.md](quickstart.md)

**Organization**: The specification has one P1 user story. Tests are required by
its Verification section and are written before the corresponding implementation.
Paths in task descriptions are relative to the repository root.

## Phase 1: Setup

**Purpose**: Establish the project and reproducible tooling.

- [X] T001 Create `pyproject.toml` with the planned runtime and development dependencies, Python compatibility, Ruff, Pyright, and pytest configuration; generate `uv.lock` and resolve the complete dependency set including Langfuse.
- [X] T002 Create the Python package entry point in `app/__init__.py` and test directories via `tests/unit/__init__.py` and `tests/integration/__init__.py`.
- [X] T003 [P] Update `.gitignore` to exclude credentials, local knowledge databases and journals, uploaded files, model caches, and Python tooling artifacts without ignoring source or fixtures.

## Phase 2: Foundational

**Purpose**: Shared configuration and deterministic test support.

- [X] T004 Implement typed, environment-based settings and local paths in `app/config.py`, including embedding and trace configuration without hard-coded credentials.
- [X] T005 [P] Create deterministic embedding and recording trace test substitutes and reusable temporary-storage fixtures in `tests/conftest.py`; default tests must not contact a model provider or observability service.
- [X] T006 [P] Create original known-evidence text and PDF samples in `data/sample-knowledge/observatory.txt` and `data/sample-knowledge/observatory.pdf`, plus any non-sensitive fixtures needed in `tests/fixtures/`.

**Checkpoint**: Setup and foundational tasks complete before the story tasks.

## Phase 3: User Story 1 - Upload and Index Knowledge (Priority: P1)

**Goal**: Submit local knowledge files, display independent outcomes, and
retrieve committed evidence with provenance while respecting consent and privacy.

**Independent test**: Submit a valid UTF-8 text file and unencrypted text PDF,
observe each success, and retrieve the known fact with filename and chunk
identifier. Also verify mixed and over-limit submissions, atomic replacement and
recovery, access and consent boundaries, and privacy-safe tracing offline.

### Tests for User Story 1

Write these tests first and confirm that the relevant cases fail before their
implementations are added. Use deterministic substitutes except for real SQLite
and explicitly opt-in live or model checks.

- [X] T007 [P] [US1] Write upload contract tests in `tests/unit/test_upload_validation.py` for count and size boundaries, count-first precedence, ordered duplicate entries, all applicable validation reasons, UTF-8 markers and decoding, encrypted PDFs, supported formats, and non-English content.
- [X] T008 [P] [US1] Write ingestion tests in `tests/unit/test_ingestion.py` for parsing, empty or corrupt content, token-limited chunking without gaps or truncation, independent outcomes, provider failures, and safe messages.
- [X] T009 [P] [US1] Write real-SQLite tests in `tests/integration/test_storage.py` for atomic replacement, rollback, committed-only reads, restarts, provenance, model incompatibility, and invalid vectors.
- [X] T010 [P] [US1] Write cross-session and cross-process reservation tests in `tests/integration/test_reservations.py` for same-name rejection, unrelated filenames, unexpected reservation errors, retries, and interruption before and after commit.
- [X] T011 [P] [US1] Write retrieval contract tests in `tests/unit/test_retrieval.py` for ranked cosine results and provenance, empty indexes, input errors, incompatible or invalid embeddings, provider and storage failures, and per-call diagnostic correlation.
- [X] T012 [P] [US1] Write external-indexing consent tests in `tests/integration/test_indexing_consent.py` using a recording provider fake to verify disclosure, per-batch and per-provider opt-in, refusal, provider changes, and no document-text calls without consent, including UI reruns.
- [X] T013 [P] [US1] Write offline trace tests in `tests/unit/test_observability.py` for entered step hierarchy, outcomes, durations, optional model and usage metadata, distinct upload and retrieval identifiers, prohibited sentinel values, and simultaneous core and tracing failures.
- [X] T014 [P] [US1] Write trace-permission tests in `tests/integration/test_trace_permission.py` for local-user confirmation, loopback and peer checks, proxy bypass and redirect rejection, absent or expired confirmation, restart and routing changes, external opt-in persistence, revocation, queued and in-flight dispatch races across processes, and disabled versus unavailable warnings.
- [X] T015 [P] [US1] Write Streamlit and launch tests in `tests/integration/test_upload_ui.py` for submitted-entry snapshots, rerun safety, accessible status and permission controls, visible warnings, and fail-closed loopback configuration; record browser and screen-reader checks that AppTest cannot establish.
- [X] T016 [P] [US1] Write an explicitly opt-in cached-real-model known-evidence test in `tests/integration/test_real_model.py`, separate from the default offline suite, without claiming general retrieval quality.

### Implementation for User Story 1

- [X] T017 [US1] Implement SQLite document and chunk persistence in `app/storage.py` using the canonical constraints in [data-model.md](data-model.md): `KnowledgeDocument.document_id`, `KnowledgeDocument.filename`, `KnowledgeDocument.indexed_at`, `KnowledgeDocument.embedding_model_id`, `KnowledgeDocument.embedding_dimension`, `KnowledgeChunk.document_id`, `KnowledgeChunk.chunk_id`, `KnowledgeChunk.text`, `KnowledgeChunk.embedding`, and `KnowledgeChunk.page`; enforce foreign keys and atomic replacement.
- [X] T018 [US1] Implement non-waiting exact-filename reservations in `app/storage.py` across threads, sessions, and processes, with crash-safe release, distinct conflict versus error outcomes, and no change to committed knowledge on rejection or failure.
- [X] T019 [P] [US1] Implement the embedding provider interface and local FastEmbed adapter in `app/embeddings.py`, including provider disclosure capabilities, model identity and dimensions, token-limit support, invalid-vector checks, and explicit unavailable-model errors.
- [X] T020 [US1] Implement submitted-entry models, opaque identifiers, ordered batch validation, lifecycle outcomes, UTF-8 and PDF parsing, and token-aware chunking in `app/ingestion.py`, following [data-model.md](data-model.md) and [knowledge-workflow.md](contracts/knowledge-workflow.md).
- [X] T021 [US1] Implement per-batch external-provider disclosure and consent, reservation, independent file processing, and atomic publication in `app/ingestion.py`; do not add a production remote provider.
- [X] T022 [US1] Implement ranked committed-evidence retrieval and fresh operation identifiers in `app/retrieval.py`, preserving the evidence result shape and making input, model, vector, provider, and storage errors explicit.
- [X] T023 [P] [US1] Implement destination classification, process-lifetime local-user confirmation, direct loopback and peer checks, proxy bypass, redirect rejection, and persistent external trace permission in `app/observability.py` according to [data-model.md](data-model.md) and [knowledge-workflow.md](contracts/knowledge-workflow.md), coordinating dispatch and invalidation across processes and discarding unsent traces.
- [X] T024 [US1] Implement the Langfuse-backed tracing interface and separate safe diagnostics in `app/observability.py`, with an explicit field allowlist, no automatic sensitive capture, accurate operation and entered-step outcomes and durations, available metadata, and explicit detected-failure warnings.
- [X] T025 [US1] Instrument `app/ingestion.py` and `app/retrieval.py` with the observability interface, preserving core success and failure outcomes and correlating each submitted entry and retrieval call even when tracing is unavailable.
- [X] T026 [US1] Implement the local Streamlit upload and permission view in `app/ui.py`: explicit batch snapshot, transport and application limits, independent textual statuses and safe warnings, keyboard- and screen-reader-accessible local trace confirmation and revocation, and separate external indexing and trace consent.
- [X] T027 [US1] Implement the supported loopback-only launch and effective-configuration check in `app/ui.py` and `app/config.py`, retaining Streamlit security protections and failing closed on unsafe binding.
- [X] T028 [P] [US1] Implement the local evidence verification command in `app/retrieval_check.py`, including argument help, explicit errors, and separate operation-correlated observability diagnostics.
- [X] T029 [US1] Run the focused offline suites in `tests/unit/` and `tests/integration/`, resolve failures, and verify that no live model download or observability service is required by default.
- [X] T030 [US1] Execute the actual-browser upload boundary, mixed-selection and resubmission checks, and keyboard and screen-reader walkthrough described in `specs/001-knowledge-upload-indexing/quickstart.md`; record observed limitations without assuming rejected files reach Python.

**Checkpoint**: US1 is independently functional and its required offline and
manual checks have been completed. A live Langfuse check remains opt-in.

## Phase 4: Polish and Cross-Cutting Concerns

- [X] T031 Update `README.md` and `.env.example` with setup, loopback launch, model download and offline behavior, English retrieval limits, process-lifetime local trace confirmation and the user's forwarding responsibility, trace destination and consent controls, safe diagnostics, and opt-in checks; include credential names only.
- [X] T032 Document the exact stopped-app local knowledge-base removal procedure and its limits in `README.md`, including database and journal/WAL files, external copies, backups, and the lack of secure-erasure guarantees.
- [X] T033 Add the planned Windows and Linux Python 3.11-3.13 matrix in `.github/workflows/ci.yml` to install the locked dependencies and run Ruff, Pyright, and the offline pytest suite; report only versions actually verified.
- [X] T034 Run the locked lint, format, type, and test commands and the applicable manual verification in `specs/001-knowledge-upload-indexing/quickstart.md`; measure sample-corpus indexing and retrieval performance without implying an unmeasured target or retrieval-quality guarantee.

## Phase 5: Convergence

- [ ] T035 Perform a physical keyboard and screen-reader walkthrough in the rendered upload, status, and trace-permission controls and record observed results or limitations per FR-017, SC-005, and US1/AC16 (partial).
- [X] T036 Complete and record the remaining manual verification cases in `specs/001-knowledge-upload-indexing/quickstart.md`, including corrupt/no-text PDFs, replacement success and failure, interruption/restart behavior, undecodable text, and encrypted PDFs per US1/AC4, US1/AC7, US1/AC17, US1/AC19-21 and SC-004 (partial).
- [X] T037 Obtain executable Windows/Linux Python 3.11-3.13 CI matrix evidence or document explicitly which matrix entries remain uncompleted, and revise verification claims under the plan: CI matrix decision and Constitution IV (partial).

## Dependencies and Execution Order

### Phase dependencies

- Setup (T001-T003) precedes foundational work (T004-T006).
- Foundational work precedes the US1 test and implementation phase.
- The US1 tests T007-T016 are written before the corresponding implementation.
- Polish and final verification follow the story implementation; T034 follows
  the documentation and CI tasks.

### User story dependencies

- US1 is the only specified story. It depends on setup and foundation, not on
  any later answer-generation feature.
- T017 precedes T018 and storage-backed integration; T019 and T020 precede T021;
  T017 and T019 precede T022; T023 precedes T024; T021, T022, and T024 precede
  T025; T025 precedes the integrated UI in T026 and the full offline run T029.
- T027 follows T026; T028 follows T022 and T024; T029 follows T026, T027, and
  T028; T030 follows T026, T027, and T029. Tasks modifying the same file are
  sequential even if listed separately.

### Parallel opportunities

- T003 can run independently of T001-T002; T005 and T006 can run alongside T004
  after setup.
- After the foundation, T007-T016 use separate test files and can be authored
  in parallel.
- After the relevant failing tests exist, T019 and T023 can proceed alongside
  T017; their integration depends on the ordering above.

## Parallel Example: User Story 1

After foundation, different contributors can independently author
`tests/unit/test_upload_validation.py`, `tests/unit/test_retrieval.py`, and
`tests/unit/test_observability.py`. Once those tests exist, separate contributors
can implement `app/storage.py`, `app/embeddings.py`, and the permission boundary
in `app/observability.py`, then integrate them in dependency order.

## Implementation Strategy

1. Complete setup and foundation, including the unified dependency lock.
2. Write the story's focused tests and implement the complete US1 workflow.
3. Validate US1 offline and perform browser/accessibility checks; this complete
   story is the MVP, not a partial upload-only subset.
4. Finish documentation, CI, and final verification. Run live-provider and
   real-model checks only when explicitly opted in.

## Notes

- `[P]` indicates distinct files and no dependency on another incomplete task in
  the same parallel group; `[US1]` identifies the feature's only user story.
- A checked task means implementation work was completed and verified, unlike
  the reviewer-owned requirements-quality checklists.
- Dependency compatibility, UI behavior, and live export have not yet been
  validated; do not claim support or delivery until the relevant checks pass.
