---
description: "Task list for Feature 002 implementation"
---

# Tasks: Evidence-Grounded Question Answering

**Input**: Design documents from `specs\002-grounded-question-answering\`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts\question-workflow.md`, and `quickstart.md`

**Tests**: Deterministic offline tests are required by FR-020 and the
constitution. Live local-model and Langfuse checks are opt-in.

**Organization**: Tasks are grouped by user story. This feature has one P1
user story. Review open requirements-readiness findings before implementation;
do not make unresolved policy decisions implicitly in code.

## Format

Every task follows `- [ ] Tnnn [P?] [Story?] Description with file path`.
`[P]` marks independent work in different files. User-story tasks use `[US1]`;
setup, foundation, and polish tasks do not.

## Phase 1: Setup

**Purpose**: Add the required orchestration dependency without changing the
supported Python range or assuming compatibility before verification.

- [X] T001 Verify CrewAI 1.15.45 API and dependency resolution against the existing Windows/Linux Python 3.11-3.13 matrix, then pin it in `pyproject.toml` and regenerate `uv.lock` only if compatible; record an evidence-based blocker in `plan.md` if it is not.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Preserve the reviewed requirements decisions and establish
deterministic offline execution before implementing the user story.

- [X] T002 Readiness process gate: Verify before implementation that the current checked resolutions for CHK004, CHK007, CHK010, CHK012, CHK013, CHK017, CHK020, CHK023, and CHK034 remain aligned across `specs\002-grounded-question-answering\spec.md`, `plan.md`, `data-model.md`, `contracts\question-workflow.md`, `quickstart.md`, and `checklists\question-readiness.md`; reopen any criterion invalidated by later changes.
- [X] T003 Extend `tests\conftest.py` and add `tests\crewai_test_support.py` with deterministic CrewAI/LLM substitutes, isolated CrewAI test storage, and network denial for unapproved model or observability calls; retain the separately mocked authorized Langfuse path.

**Checkpoint**: Readiness decisions are recorded and the default test harness
cannot silently call a live model or observability service.

---

## Phase 3: User Story 1 - Ask Questions About Indexed Knowledge (Priority: P1) MVP

**Goal**: Let a local user submit one question at a time and receive only
directly supported, cited claims, partial answers or abstention, with fresh
citations, safe failures, and privacy-controlled workflow traces.

**Independent Test**: Populate a temporary SQLite index with the
non-sensitive evaluation corpus and deterministic embedding, CrewAI/model,
storage, and trace substitutes. Verify answerable, partial, unanswerable, and
multi-source questions; blank input; fabricated and indeterminate citations;
untrusted document instructions; workflow failures; source replacement;
single-active-request behavior; trace isolation; and evaluation-field gates.
The test suite must run without a live model, model download, or live Langfuse.

### Tests for User Story 1

Write these focused offline tests before the corresponding implementation and
verify that they fail for the missing behavior.

- [X] T004 [P] [US1] Add SQLite migration, replacement, revision, rollback, snapshot-consistency, and citation-freshness tests in `tests\integration\test_question_storage.py`.
- [X] T005 [P] [US1] Add versioned retrieval tests for evidence provenance, same-snapshot revision binding, empty knowledge, incompatible indexes, and preserved Feature 001 retrieval behavior in `tests\unit\test_question_retrieval.py`.
- [X] T006 [P] [US1] Add deterministic workflow tests for structured drafts and verification, direct-evidence-only support, citations, partial answers, abstention, empty knowledge, untrusted instructions, malformed outcomes, and failure-specific safe guidance for model setup, index recovery, timeouts, repeated task/model failures, and tracing in `tests\unit\test_question_workflow.py`.
- [X] T007 [P] [US1] Add local-runtime boundary tests for unavailable models, remote/cloud rejection, loopback and peer validation, proxy/redirect handling, token and time limits, and no-download/no-fallback behavior in `tests\unit\test_local_model.py`.
- [X] T008 [P] [US1] Add offline trace tests for content-free local records, allowlisted entered stages, export failures and disabled/unavailable/failed/unconfirmed/confirmed states, ordinary-question isolation, evaluation-field confirmation, source eligibility, authorization, and revocation in `tests\unit\test_question_observability.py`.
- [ ] T009 [P] [US1] Add Streamlit/session tests for blank input, progress and terminal states, explicit-only submission, one active request, request/result ownership, safe errors, labeled controls, visible keyboard focus, announced status/errors, and cited-source freshness before publication and after display, reruns, edits, submission, navigation, and keyboard/pointer activation (with passive focus, hover, and scrolling excluded) in `tests\integration\test_question_ui.py`.
- [X] T010 [P] [US1] Add evaluation-corpus validation tests for case IDs, categories, expected answer points/sources, the explicit no-support case, and a multi-source case with distinct directly supported points from separate sources (no cross-source inference) in `tests\unit\test_feature_002_evaluation.py`.
- [X] T011 [P] [US1] Add evaluator CLI tests for explicit local-model opt-in, the workflow-contract JSONL schema and review-status enums, pending versus unavailable handling, no automatic model download, and no final-report generation in `tests\unit\test_feature_002_evaluator.py`.
- [X] T012 [P] [US1] Add an explicitly opt-in local-model smoke test in `tests\integration\test_real_question_model.py` that requires the preinstalled model, performs no download, uses non-sensitive evaluation data, and records only observed behavior.
- [X] T013 [P] [US1] Add an explicitly opt-in authorized Langfuse smoke test in `tests\integration\test_live_question_trace.py` using non-sensitive evaluation data; verify permitted payloads and require explicit server acknowledgment for confirmed delivery, leaving queue/flush-only delivery unconfirmed.

### Implementation for User Story 1

- [X] T014 [US1] Add the transactional document-revision migration, replacement revision, and committed freshness-read support in `app\storage.py`; preserve existing rows and rollback behavior, following `data-model.md` definitions for `CommittedDocument.document_id`, `CommittedDocument.filename`, `CommittedDocument.revision`, `Chunk.chunk_id`, `Chunk.text`, `Chunk.page`, and `Chunk.embedding`.
- [X] T015 [US1] Add an internal versioned evidence-snapshot path in `app\retrieval.py` that binds ranking inputs, evidence content, and source revision from one committed snapshot while preserving Feature 001's public `retrieve()` behavior; follow `data-model.md` fields `Evidence.text`, `Evidence.filename`, `Evidence.chunk_id`, `Evidence.score`, `EvidenceSnapshot.document_id`, `EvidenceSnapshot.revision`, and `EvidenceSnapshot.digest`.
- [X] T016 [P] [US1] Implement the manually prepared Ollama adapter and explicit local-only configuration in `app\local_model.py` and `app\config.py`; validate the configured model and loopback peer, disable proxies and redirects, reject remote/cloud models, enforce the specified execution limits, and never download or fall back.
- [X] T017 [P] [US1] Implement the owner-approved safe error-code-to-guidance mapping in `app\question_errors.py`; implement the failure-specific actions in FR-013 and keep raw exceptions, credentials, question text, and document content out of user-visible messages.
- [X] T018 [US1] Implement the bounded CrewAI Flow and sequential draft/verify tasks in `app\question_workflow.py`; inject the local model explicitly, validate complete outcomes and claim-level direct support, and expose only checked claims and citations, following `data-model.md` fields `QuestionRequest.request_id`, `QuestionRequest.question`, `Draft.atomic_claims`, `Draft.candidate_citation_keys`, `ClaimVerification.claim_id`, `ClaimVerification.decision`, `ClaimVerification.citation_keys`, `Citation.filename`, `Citation.chunk_id`, `Citation.revision`, `Citation.digest`, `AnswerOutcome.status`, `AnswerOutcome.supported_claims`, `AnswerOutcome.missing_explanation`, and `AnswerOutcome.error_code`.
- [X] T019 [US1] Implement the atomic per-session active-job registry and request-correlated worker lifecycle in `app\question_jobs.py`; reject overlapping submissions, ignore late or mismatched results, and release owned resources at termination, following `data-model.md` fields `SessionJob.session_id`, `SessionJob.request_id`, `SessionJob.worker`, and `SessionJob.state`.
- [X] T020 [US1] Extend `app\observability.py` with non-persisted content-free local question traces and authorized Langfuse export while preserving Feature 001 permissions and exclusions; use `data-model.md` fields `TraceRecord.operation_id`, `TraceRecord.stages`, `TraceRecord.export_status`, `TraceStage.name`, `TraceStage.status`, `TraceStage.elapsed_ms`, `TraceStage.model_id`, and `TraceStage.usage_details`.
- [X] T021 [US1] Add evaluation-trace disclosure, per-run field confirmation, and full-source eligibility checks in `app\observability.py`; recheck selected case, source revision/content, and destination authorization inside the serialized dispatch boundary, following `data-model.md` fields `QuestionRequest.evaluation_case_id`, `QuestionRequest.evaluation_fields_confirmed`, `EvaluationTracePayload.question`, and `EvaluationTracePayload.source_ids`.
- [X] T022 [US1] Add the distinct Ask Questions view in `app\ui.py` with blank-input validation, explicit submission, progress, cited supported/partial answers, abstention, empty-knowledge state, and the specified accessible controls/status/errors; retain upload-view behavior and require the approved evaluation disclosure/confirmation flow.
- [X] T023 [US1] Integrate citation freshness checks before publication and on every rerun or required state-changing action in `app\ui.py`; hide affected claims, warn and request resubmission, and disclose the idle-view limitation, adding `app\question_freshness_component.py` only if required Streamlit interactions otherwise cannot trigger validation. Pass the action-trigger tests in `tests\integration\test_question_ui.py`.
- [X] T024 [US1] Create original, redistributable, non-sensitive evaluation sources and `evaluation\feature_002\cases.jsonl` with at least five cases covering three answerable, one unanswerable, and one multi-source question; include expected answer points and sources, ensure the multi-source case has at least two distinct points directly stated in separate sources, and explicitly mark no support for the unanswerable case, following `data-model.md` fields `EvaluationCase.id`, `EvaluationCase.question`, `EvaluationCase.categories`, `EvaluationCase.expected_answer_points`, `EvaluationCase.expected_sources`, and `EvaluationCase.no_support`.
- [X] T025 [US1] Implement `scripts\evaluate_feature_002.py` to require `--confirm-local-model`, use only the manually prepared local model and `evaluation\feature_002\cases.jsonl`, and emit the workflow-contract JSONL schema with enumerated human-review statuses initialized as pending, distinct unavailable statuses, safe `failure_code` or null, and measured `elapsed_ms` or null; do not infer review outcomes or generate the final report.

**Checkpoint**: User Story 1 works with deterministic offline substitutes;
live integrations remain explicitly opt-in.

---

## Phase 4: Polish and Cross-Cutting Concerns

**Purpose**: Document operations and verify that Feature 001 remains intact.

- [X] T026 Update `README.md` and `specs\002-grounded-question-answering\quickstart.md` with manual model setup, resource caveats, environment configuration, privacy/trace disclosures, offline commands, opt-in checks, accessibility validation, and safe failure guidance.
- [ ] T027 Run Ruff lint and format checks, Pyright, the complete offline pytest suite, documented quickstart checks, and the Windows/Linux Python 3.11-3.13 CI matrix; resolve regressions without weakening Feature 001 behavior and record only measured results in `specs\002-grounded-question-answering\quickstart.md`.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 has no feature-task dependencies.
- **Foundational (Phase 2)**: T002 and T003 block the user story. T003 also
  requires the compatible CrewAI dependency from T001.
- **User Story 1 (Phase 3)**: All story work follows T002 and T003. Offline
  tests and corpus/CLI tests are written before their implementations;
  opt-in live tests are authored but skipped by default.
- **Polish (Phase 4)**: T026-T027 depend on completion of the required P1
  behavior; live-service checks remain opt-in and are not required for offline
  verification.

### User Story Dependencies

- **User Story 1 (P1)**: Depends on the foundational readiness review and
  deterministic test harness. No other user story exists.

### Within User Story 1

- T004-T011 can be prepared in parallel after T002-T003 because they use
  separate offline test files. T012-T013 are opt-in checks and remain skipped
  unless the required local model or authorized Langfuse destination is available.
- T014, T016, T017, T020, and T024 can proceed in parallel after their
  corresponding tests and prerequisite decisions.
- T015 depends on T014. T018 depends on T015-T017. T019 depends on T018.
- T021 depends on T020 and T024. T022 depends on T017-T021. T023 depends on
  T014, T015, and T022.
- T025 depends on T016, T018, and T024; live checks remain opt-in.
- T026-T027 follow the completed implementation and verification work.

## Parallel Example: User Story 1

```text
After T002-T003, prepare independent offline tests:
Task: T004 storage migration and freshness tests in tests\integration\test_question_storage.py
Task: T005 versioned retrieval tests in tests\unit\test_question_retrieval.py
Task: T006 grounding and workflow tests in tests\unit\test_question_workflow.py
Task: T007 local model boundary tests in tests\unit\test_local_model.py
Task: T008 trace privacy tests in tests\unit\test_question_observability.py
Task: T009 UI/session tests in tests\integration\test_question_ui.py
Task: T010 evaluation dataset tests in tests\unit\test_feature_002_evaluation.py
Task: T011 evaluator CLI tests in tests\unit\test_feature_002_evaluator.py
Task: T012 opt-in local-model test in tests\integration\test_real_question_model.py
Task: T013 opt-in Langfuse test in tests\integration\test_live_question_trace.py

After corresponding offline tests pass, independent implementation can begin;
the opt-in live checks may remain skipped:
Task: T014 SQLite revisions in app\storage.py
Task: T016 local model adapter in app\local_model.py and app\config.py
Task: T017 safe errors in app\question_errors.py
Task: T020 allowlisted traces in app\observability.py
Task: T024 evaluation corpus in evaluation\feature_002\
```

## Implementation Strategy

### MVP First

The MVP is the single P1 user story: complete T001-T003, implement the
offline-testable question workflow, citations, freshness, privacy gates, UI,
and evaluation corpus, then verify the full offline acceptance criteria.
Do not require a live model or Langfuse service for the MVP verification.

### Incremental Delivery

1. Complete dependency setup, verify the reviewed readiness decisions remain
   current, and establish the deterministic offline harness.
2. Implement source revisions and versioned retrieval, then the local model,
   verified answer workflow, session job, trace controls, and Ask Questions UI.
3. Add the evaluation corpus and explicit local evaluator.
4. Add opt-in live checks and finish documentation and CI verification.

The final evaluation report is outside this task list and is not generated
automatically.

## Notes

- Every task uses the checkbox, sequential ID, optional parallel marker,
  user-story label where applicable, and a repository path.
- `[P]` marks independent work in different files with no unfinished
  prerequisite.
- `data-model.md` is canonical for field constraints; implementing tasks cite
  exact `Entity.field` identities rather than duplicating their constraints.
- Reviewer-owned readiness markers represent requirements review only; reopen
  them when a later change invalidates a criterion. Do not treat checked
  markers as implementation or verification completion.
