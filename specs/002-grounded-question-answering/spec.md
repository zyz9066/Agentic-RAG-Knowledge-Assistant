# Feature Specification: Evidence-Grounded Question Answering

**Feature Branch**: `002-grounded-question-answering`

**Created**: 2026-11-26

**Status**: Draft

**Input**: A local user asks questions about previously indexed knowledge and
receives evidence-grounded answers with source references, or a cautious
response when evidence is insufficient.

## Clarifications

### Session 2026-11-26

- Q: How should the assignment's trace-content requirement be reconciled with
  Feature 001's exclusions? A: Allow questions and source metadata in traces
  only for explicitly selected non-sensitive evaluation examples. Keep ordinary
  question traces and Feature 001 traces content-free.
- Q: When the documents support only part of an answer, what should the user
  see? A: Show only supported parts with citations and explain what is missing.
- Q: How should the app decide whether an indexed source is safe to identify
  in an evaluation trace? A: Verify its indexed content matches the known
  evaluation source; omit source identifiers when it cannot be verified.
- Q: What should happen when the answer checker cannot determine whether a
  claim is supported? A: Omit uncertain claims, show supported parts and
  explain what could not be established, or abstain if none remain.
- Q: What should happen if a user tries to submit another question while one
  is still processing in the same session? A: Block the new submission and
  ask the user to wait until the current question finishes.
- Q: If the local answer model is not installed, how should the application
  obtain it? A: Require manual model setup; show a clear error and setup
  guidance instead of automatically downloading it.
- Q: How should citations behave when a source is replaced during or after
  question processing? A: Do not show affected claims as current; warn that the
  source changed and ask the user to rerun the question.
- Q: When should the application check already displayed answers for changed
  sources? A: On the next rerun or state-changing action, including input edits,
  submissions, navigation, and keyboard or pointer activation; not on passive
  focus, hover, or scrolling. An idle view may be stale until then.

### Session 2026-11-28

- Q: Should every question create a content-free local trace record when Langfuse is unavailable or not authorized, while Langfuse export remains permission-gated? → A: Create a non-persisted content-free trace for each workflow; export it to Langfuse only when available and authorized, and discard it when the session ends.
- Q: Should exporting the question and verified source IDs for a selected evaluation case require a fresh field-specific confirmation for each run, in addition to existing destination authorization? → A: Yes. Require per-run confirmation of the disclosed question and source-ID fields, as well as existing destination authorization.
- Q: When evidence is incomplete or conflicting, what rule should determine whether an answer claim is supported? → A: Count a claim as supported only when its cited evidence directly states it; allow faithful paraphrase but not inference across passages. Treat unresolved contradictions in the cited evidence as indeterminate.
- Q: What fixed limits should the question workflow enforce for each model call and for the complete request? → A: Limit each model call to 120 seconds, the total worker to 300 seconds, retries to one per task, input to 8,192 tokens, and output to 1,024 tokens.
- Q: Which user actions should trigger a freshness check for an answer that is already displayed? → A: Check on app reruns and state-changing actions, including input edits, submissions, navigation, and keyboard or pointer activation; exclude passive focus, hover, and scrolling.
- Q: What safe next step should the app give for each major workflow failure—model unavailable, retrieval/index error, task timeout, and tracing failure? → A: Give failure-specific safe actions: follow documented manual setup for an unavailable or misconfigured local model; check or rebuild an incompatible index through the documented knowledge workflow; retry a timed-out question with less evidence or after the service is available; for other repeated task/model failures, retry or contact the maintainer with the opaque operation ID; and report tracing problems separately with a safe configuration/authorization check. Never expose raw exceptions, credentials, question text, or document content.
- Q: What evidence should let the app label a Langfuse trace as confirmed delivered? → A: Require an explicit server acknowledgment tied to the trace; if the SDK cannot provide one, keep the state unconfirmed. A successful local queue or flush is not proof of delivery.
- Q: What explicit accessibility behavior should the Ask Questions view require for its input, progress, answers, citations, warnings, and trace disclosures? → A: Provide programmatically labeled controls, keyboard operation with visible focus, screen-reader announcements for progress/status/errors, readable source references, and warnings/statuses that do not rely on color alone. Verify these behaviors without claiming formal WCAG certification.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask Questions About Indexed Knowledge (Priority: P1)

As a user with indexed knowledge, I want to ask a natural-language question and
receive an answer grounded in my uploaded documents, with source references, so
that I can understand and verify the answer.

**Why this priority**: Answers with verifiable evidence are the primary value
of the knowledge assistant; uncertainty must be visible when evidence is
insufficient.

**Independent Test**: Index the evaluation knowledge, submit its answerable,
unanswerable, and multi-source questions, and compare the answers and citations
with their expected answer points and sources. Exercise failures and trace
isolation with deterministic substitutes.

**Acceptance Scenarios**:

1. **Given** indexed knowledge contains supporting evidence, **When** the user
   submits an answerable question, **Then** the user sees an answer supported
   by that evidence and source references with filenames and chunk identifiers.
2. **Given** a question requires at least two distinct factual points from
   multiple chunks or documents, **When** those sources are available to the
   workflow, **Then** each point is directly supported by its cited evidence
   and the answer includes the points without inference across sources.
3. **Given** the available evidence does not support a complete answer,
   **When** the user submits a question, **Then** the system may show supported
   parts with citations, explains what is missing, and does not present
   unsupported claims as facts. If no part is supported, it abstains.
4. **Given** the knowledge base is empty, **When** the user submits a question,
   **Then** the user is told that no supporting knowledge is available.
5. **Given** a blank or whitespace-only question, **When** it is submitted,
   **Then** a validation message is shown and no answer workflow starts.
6. **Given** retrieved content instructs the assistant to ignore its rules,
   **When** that content is used for a question, **Then** it is treated as
   untrusted document content, not as an instruction to the workflow.
7. **Given** a proposed claim cites a non-retrieved or non-supporting source,
   **When** the answer is verified, **Then** the claim and citation are not
   presented as verified; uncertainty or abstention is shown as appropriate.
   The same outcome applies when the checker cannot determine support.
8. **Given** retrieval, the answer model, or a workflow task fails, **When**
   the question is processed, **Then** the user sees a safe, actionable error
   rather than a successful answer or an unsupported-evidence message.
9. **Given** tracing is unavailable or fails, **When** question processing
   succeeds or fails, **Then** the actual outcome is preserved and a separate
   safe diagnostic reports the trace problem.
10. **Given** deterministic substitutes and the evaluation dataset, **When**
    offline verification runs, **Then** it checks supported answers, citations,
    abstention, workflow failures, and trace isolation without contacting a
    live model or observability service.
11. **Given** a submitted valid question, **When** the answer workflow is
    running, **Then** the user can see a textual processing state until a
    final answer, abstention, or error is available.
12. **Given** a user explicitly selects a non-sensitive evaluation example
    and confirms its disclosed trace fields, **When** an authorized trace is
    exported for that example, **Then** it may include that example's question
    and eligible source metadata, but not document text or unrelated content.
13. **Given** an ordinary question or an example not explicitly selected for
    trace-content export, **When** its workflow is traced, **Then** the question
    and source identifiers are excluded and existing permission rules remain
    in force. Any source whose eligibility cannot be verified is excluded even
    for a selected example.
14. **Given** a question is processing in a session, **When** another question
    is submitted in that same session, **Then** it is not started or queued,
    and the user is told to wait for the active question to finish.
15. **Given** the local answer model is not installed or available, **When**
    the user submits a question, **Then** the app reports the problem and
    provides setup guidance without automatically downloading a model.
16. **Given** a cited source is replaced before an answer is published,
    **When** publication checks the source, **Then** affected claims are not
    displayed as current, the user is warned, and a new question submission is
    requested.
17. **Given** a cited source changes after an answer is displayed, **When** the
    user next performs a state-changing app action or the app reruns, **Then**
    affected claims are no longer displayed as current, a warning is shown,
    and the user is asked to rerun the question. The view discloses that an idle
    answer can be stale until the next required check. Passive focus, hover,
    and scrolling alone do not trigger a check.
18. **Given** a user operates the Ask Questions view with a keyboard or screen
    reader, **When** they enter and submit a question, review progress and
    results, inspect citations, or confirm evaluation trace fields, **Then**
    controls have programmatic labels, keyboard focus is visible, status and
    error changes are announced, source references are readable, and warnings
    are not conveyed by color alone.

### Edge Cases

- An unrelated question can still retrieve ranked candidates; candidates and
  their similarity scores do not establish relevance or sufficiency.
- Conflicting or partial evidence must not be presented as a fully supported
  unqualified answer. Missing support must be communicated.
- A fabricated, stale, ambiguous, or non-supporting citation must not be
  presented as a verified source for a claim.
- An unavailable local model, incompatible index, failed retrieval, malformed
  workflow outcome, or bounded execution limit must produce a safe failure
  rather than an invented answer or an empty-knowledge claim.
- Repeated UI interactions must not repeat a submission without an explicit
  new submission or associate one request's result with another request.
- Trace unavailability must not prevent use of the question workflow; disabled
  export must remain distinguishable from a detected export failure.
- If an evaluation question retrieves non-evaluation knowledge or the origin of
  a source cannot be established, that source's metadata must not be exported.
- A source with a familiar filename may have been replaced with different
  content; matching the name alone does not establish trace eligibility.
- A source can be replaced while an answer is being generated or after it is
  displayed. Check before publication and again on the next app rerun or
  state-changing action, including input edits, submissions, navigation, and
  keyboard or pointer activation. Passive focus, hover, and scrolling alone do
  not trigger a check; an idle display can remain stale until the next required
  check.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an Ask Questions view clearly separate
  from the existing upload view, with a question input and explicit submission.
  The input, submission control, and evaluation trace disclosures MUST have
  programmatic labels, keyboard operation, and visible focus.
- **FR-002**: The system MUST reject blank or whitespace-only questions with a
  visible message before beginning the answer workflow.
- **FR-003**: The system MUST use the existing committed knowledge base and
  retrieval behavior without rebuilding or weakening Feature 001's upload,
  indexing, retrieval, privacy, or consent guarantees.
- **FR-004**: The system MUST preserve exact source filename and chunk
  identifiers from retrieved evidence through the displayed references. Check
  source identity and content for changes before publication and on each
  subsequent app rerun or state-changing action, including input edits,
  submissions, navigation, and keyboard or pointer activation. Passive focus,
  hover, and scrolling alone do not trigger a check. If a cited source has
  changed, do not present affected claims as current; warn the user and request
  a new question submission. Disclose that an idle view may be stale until the
  next required check.
- **FR-005**: The answering workflow MUST use CrewAI, with explicit agent and
  task inputs and outcomes and bounded execution, to retrieve evidence, produce
  an answer, and verify it against the evidence. Each model call MUST be
  limited to 120 seconds and the complete worker to 300 seconds. Allow at most
  one retry per task, limit model input to 8,192 tokens and generated output
  to 1,024 tokens, and fail safely on overflow rather than silently truncating
  evidence or accepting late results.
- **FR-006**: Answer generation MUST use a local model. Questions and document
  content MUST NOT be sent to an external answer-model provider. The user
  prepares the model separately; the application MUST NOT automatically
  download an answer model. If it is unavailable, show a clear error and setup
  guidance.
- **FR-007**: The system MUST treat retrieved content as untrusted data and MUST
  NOT follow document instructions that conflict with application rules.
- **FR-008**: The system MUST display factual claims only when supported by
  retrieved evidence and MUST identify their supporting source references.
- **FR-009**: The system MUST verify that cited references belong to the
  retrieved evidence and support the associated claims; a fabricated,
  non-retrieved, non-supporting, or indeterminate claim and citation MUST NOT
  be displayed as verified. A claim is supported only when its cited evidence
  directly states it; faithful paraphrase is permitted, but inference across
  passages is not. Unresolved contradictions in cited evidence make the claim
  indeterminate. Omit indeterminate claims; show supported parts with an
  explanation, or abstain if none remain.
- **FR-010**: If the available evidence is insufficient, incomplete, or
  conflicting, the system MUST show only supported parts with citations and
  explain what is missing or uncertain; if no part is supported, it MUST
  abstain. A retrieval rank or score alone MUST NOT be treated as proof of
  sufficiency.
- **FR-011**: An empty knowledge base MUST produce a clear no-knowledge message,
  distinct from retrieval, model, or workflow errors.
- **FR-012**: The view MUST show a textual processing state while a submitted
  question is running and a final answer, abstention, or error when it ends.
  Progress, status, and error changes MUST be announced to screen readers;
  source references MUST be readable text, and warnings/statuses MUST NOT rely
  on color alone.
- **FR-013**: Retrieval, model, task, and execution-limit failures MUST produce
  safe actionable errors without raw document content, credentials, or internal
  exception details, and MUST NOT be represented as successful answers.
  Guidance MUST be failure-specific: an unavailable or misconfigured local
  model points to documented manual setup; an incompatible retrieval index
  points to the documented knowledge/index recovery workflow; a timeout
  recommends retrying with less evidence or after the service is available;
  other task or model failures recommend retrying or contacting the maintainer
  with the opaque operation ID;
  and a tracing failure is reported separately with a safe configuration or
  authorization check without changing the answer outcome.
- **FR-014**: UI reruns MUST NOT automatically resubmit a question; each
  explicitly submitted request MUST retain its own associated outcome. Allow
  only one active question per session; reject additional submissions with a
  wait message until the active question reaches a final outcome.
- **FR-015**: The system MUST create a content-free, non-persisted trace for every
  submitted question, including when Langfuse is unavailable or unauthorized.
  When Langfuse is available and authorized, it MUST export the end-to-end
  question-workflow trace, including entered agent/task and retrieval steps,
  status, latency, and model and usage metadata where available. It MUST NOT
  fabricate unavailable metadata or claim trace delivery without confirmation.
  Delivery is confirmed only by an explicit server acknowledgment tied to that
  trace; local queueing or a successful flush alone is insufficient. If the
  exporter cannot expose such an acknowledgment, the delivery state MUST
  remain unconfirmed. Disabled, unavailable, failed, unconfirmed, and confirmed
  states MUST remain distinguishable.
- **FR-016**: Existing destination authorization, revocation, local
  confirmation, safe diagnostics, and data-minimization protections MUST
  continue to apply. Tracing failures MUST be reported separately and MUST NOT
  change the answer workflow's success or failure.
- **FR-017**: Ordinary question-workflow traces and all existing Feature 001
  traces MUST continue to exclude questions, source filenames and chunk
  identifiers, document text, credentials, and all other fields prohibited by
  Feature 001. The only exception for question and source identifiers is the
  explicitly selected evaluation-example case in FR-021.
- **FR-018**: The system MUST provide an evaluation dataset of at least five
  questions: at least three answerable, at least one unanswerable, and at least
  one requiring multiple chunks or documents. Each MUST include expected
  answer points and expected source document(s); the unanswerable case MUST
  identify that no source supports the requested answer. The multi-source case
  MUST require at least two distinct expected answer points directly stated in
  separate supporting chunks or documents; it MUST NOT require inference
  across sources.
- **FR-019**: Evaluation knowledge MUST be accessible, non-sensitive, and
  suitable for redistribution. Evaluation results MUST distinguish measured
  outcomes from unavailable metrics and MUST NOT invent measurements.
- **FR-020**: Core automated verification MUST run without a live model or
  observability service, using deterministic substitutes where appropriate.
  Live-service checks MUST be explicitly opt-in.
- **FR-021**: For a user-selected, non-sensitive evaluation example, a
  question-workflow trace MAY include the example question and source filename
  and chunk identifiers only for sources verified to belong to its evaluation
  knowledge. Before selection, disclose the example, trace destination, and
  fields to be exported. Require a separate, field-specific confirmation for
  that execution in addition to explicit example selection and existing
  trace-destination authorization. Neither selection nor field confirmation
  grants standing permission for other questions.
  Verify that the indexed source content matches the known non-sensitive
  evaluation source before allowing its identifiers in the trace; a filename
  match alone is insufficient.
  Never export document text, credentials, or unrelated or unverified source
  metadata under this exception.
- **FR-022**: If the example's eligibility, selected status, field-specific
  confirmation, or destination authorization cannot be established, export no
  question or source identifiers. Omit any source identifiers whose origin or
  indexed content cannot be verified. Report a safe diagnostic when requested
  content export cannot proceed; do not alter the question outcome.

### Key Entities

- **Question request**: A user's submitted question, its opaque request
  identifier, processing state, and final outcome.
- **Evidence**: A retrieved chunk and its source filename and chunk identifier;
  its rank or similarity does not itself establish answer sufficiency.
- **Answer outcome**: A supported answer with claim-associated references, an
  uncertainty or abstention response, or a safe processing error.
- **Workflow trace**: Content-free, non-persisted observations associated with
  every request and its entered steps, separate from the user-facing result.
  Export to Langfuse remains subject to availability and authorization; the
  local trace is discarded when the session ends.
- **Evaluation case**: A question, expected answer points, expected source
  documents or an explicit absence of support, and its answerability category.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The evaluation set contains at least five independently
  identifiable questions, including the categories in FR-018 and expected
  answer points and sources for every case.
- **SC-002**: For every answerable evaluation case, reviewers can record whether
  each expected answer point is supported and whether its cited sources are
  correct; reviewers also inspect every displayed factual claim, including
  claims not listed as expected points, using the direct-support rule in FR-009.
  For each unanswerable case, reviewers can record abstention quality.
- **SC-003**: In deterministic acceptance checks, all blank questions are
  rejected before workflow execution, and all simulated retrieval, model, and
  task failures and execution-limit violations produce a visible error rather
  than a successful answer.
- **SC-004**: In deterministic citation and prompt-injection checks, every
  supplied fabricated or non-supporting citation is rejected as verified, and
  each supplied document instruction is treated as data rather than authority.
- **SC-005**: In deterministic observability checks, every request creates an
  operation-correlated content-free trace of the steps entered; authorized
  Langfuse exports contain only permitted fields, and each simulated export
  failure leaves the core outcome unchanged. Tests distinguish disabled,
  unavailable, failed, unconfirmed, and explicitly acknowledged delivery;
  queueing or flush without acknowledgment remains unconfirmed.
- **SC-006**: A user can submit a question, observe its progress, and inspect
  its answer or uncertainty and source references without using the upload
  workflow using keyboard and screen-reader access. Verify labeled controls,
  visible keyboard focus, announced status/error changes, readable source
  references, and non-color-only warnings; record observed completion and
  accessibility limitations without claiming formal WCAG certification or
  inventing a time target or satisfaction percentage.
- **SC-007**: Deterministic privacy checks verify that selected eligible
  evaluation examples expose only the permitted question and source identifiers
  when the user confirms the fields for that run and the destination is
  authorized, and that ordinary questions, unselected examples, unconfirmed
  examples, same-named sources with different content, unrelated sources,
  document text, and credentials remain excluded.
- **SC-008**: Deterministic checks replace a cited source before publication
  and after display. In both cases the next required check removes affected
  claims from the current answer and warns the user to resubmit; the view
  discloses the idle-view limitation.

## Assumptions

- The existing local, single-user access and knowledge-storage model remains
  unchanged. No authentication or multi-user access is introduced.
- Questions are independent; persistent conversation history and multi-turn
  memory are outside this feature.
- A compatible local answer model is manually prepared by the user; its
  absence is reported with setup guidance. Model selection and execution
  details belong in planning.
- Question and source identifiers in traces are restricted to explicitly
  selected non-sensitive evaluation examples. This does not claim that every
  ordinary question trace contains the metadata requested by the assignment.
- The evaluation-report skill is not invoked automatically. Generating the
  final report is outside this feature and requires explicit user invocation
  after implementation and testing.
- No general accuracy, latency, or retrieval-quality guarantee is implied by
  passing a small evaluation set.
