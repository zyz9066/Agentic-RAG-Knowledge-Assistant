# Question Workflow Contracts

These contracts describe implementation targets, not existing APIs.
Feature 001's [knowledge workflow](../../001-knowledge-upload-indexing/contracts/knowledge-workflow.md)
continues unchanged unless an internal extension is specified here.

## Submission and UI

- Provide a clearly separate Ask Questions view. An explicit submission
  snapshots one nonblank question and allocates an opaque request ID. Reject
  whitespace before starting retrieval, an agent, or a model.
- The server atomically accepts at most one active request per session.
  Overlapping submits are rejected with a wait message; never queue them.
  UI disablement alone is insufficient. Interaction and reruns do not repeat
  submission. Worker results carry request IDs and cannot overwrite a
  different active request.
- Display accessible textual progress while processing; final states include
  cited answer, partial answer with missing information, abstention, empty
  knowledge, and safe actionable failure. Do not publish draft or unchecked
  verification text. The question, submit, and evaluation-disclosure controls
  have programmatic labels, keyboard operation, and visible focus. Announce
  progress/status/error changes to screen readers; render source references as
  readable text; do not communicate warnings or status by color alone. Verify
  these behaviors without claiming formal WCAG certification.
- Previously displayed claims are checked before publication, on every app
  rerun, and on state-changing actions: question edits, submission, navigation,
  and keyboard/pointer activation. Passive focus, hover, and scrolling do not
  trigger checks. Where Streamlit does not ordinarily rerun for a required
  action, an app-owned v2 interaction component immediately hides the prior
  answer and triggers validation; restore only freshly checked claims. Avoid
  reading or transmitting input content in the interaction trigger. Tests
  cover the required actions, reruns, cleanup, and duplicate event handling.
  Clearly disclose that an idle view can become stale.

## Retrieval and agentic workflow

- Preserve Feature 001's `retrieve` input/output, ranking and explicit errors.
  An internal versioned path reads ranking inputs, text, IDs and revisions
  from the same committed database snapshot; concurrent replacement must not
  attach a later revision to earlier text.
- Empty committed knowledge yields the distinct no-knowledge outcome.
  Incompatible index, embedding, retrieval, model, task and timeout errors
  remain failures, not empty knowledge or abstention.
- User guidance is failure-specific: direct an unavailable/misconfigured local
  model to documented manual setup; an incompatible index to the documented
  index recovery workflow; a timeout to retrying with less evidence or after
  service recovery; and other repeated task/model failures to retry or contact
  the maintainer using only the opaque operation ID. Report trace problems
  separately with a safe configuration/authorization check.
- A CrewAI Flow orchestrates deterministic retrieval followed by two sequential
  bounded agent tasks. The drafting task returns atomic claims and candidate
  citation IDs; the verifier classifies each claim against the cited retrieved
  content as supported, unsupported or indeterminate. Evidence is delimited
  untrusted data; document instructions have no authority. The model gets no
  external or write tools, delegation, memory, or code execution.
- Enforce ceilings of 120 seconds per model call, 300 seconds per worker, one
  retry per task, 8,192 input tokens (instructions, question, and evidence),
  and 1,024 generated output tokens. Fail on overflow; do not silently truncate
  supporting evidence.
- Application code validates complete structured outputs, one decision per
  claim, citation membership and source identities. It excludes unsupported,
  indeterminate, missing, fabricated, ambiguous, or stale claims. A claim with
  several citations is retained only when all required references pass.
  Supported portions may be shown with a truthful explanation of gaps; if
  none remain, abstain. Similarity scores never establish support.
- Treat automated entailment and prompt-injection defenses as probabilistic.
  Deterministic fixtures prove the application's handling of supplied
  decisions; opt-in model evaluations assess actual semantic behavior.

## Source replacement and publication

- Each committed document replacement, including an identical-content
  replacement, changes its opaque revision atomically with the complete
  chunk set. Failed replacement leaves the old revision and content intact.
  Migrate existing rows transactionally without losing documents or embeddings.
- Before publishing, on every subsequent app rerun, and on state-changing
  actions (question edits, submission, navigation, keyboard/pointer
  activation), read all cited document revisions and exact chunk-content
  digests in one fresh committed snapshot. Passive focus, hover, and scrolling
  do not trigger checks. A mismatch or missing source invalidates the entire
  affected claim; preserve unaffected claims, warn that a source changed, and
  request resubmission. If verification itself fails, hide claims and show a
  safe error. A new request is not started automatically.
- The freshness read is a point-in-time check. Do not hold a database lock
  across model inference or claim instantaneous invalidation: a replacement
  can commit after the check or while the view is idle. The UI discloses
  staleness until the next interaction or rerun.

## Local model and execution boundary

- Use a manually prepared local Ollama executable and a local model. The
  application never invokes pull/create, automatically downloads an answer
  model, or falls back to another provider. Use an app-owned runtime launched
  on literal loopback with cloud functionality disabled; verify local model
  inventory and reject remote or ambiguous model entries. Treat the runtime,
  host and local cache as trusted operator-controlled components.
- The adapter uses direct loopback connections with environment proxies and
  redirects disabled, verifies the connected peer, rejects non-loopback
  configuration, and does not send question or evidence until validation
  succeeds. Explicitly configure every agent's model; no implicit converter,
  agent, memory, embedding or judge may route to an external provider.
- Bound context, input and output sizes, iterations, retries, model-call
  timeouts and overall worker lifetime. Fail safely on overflow rather than
  silently truncating supporting evidence. If a timeout occurs, terminate the
  owned worker, disregard late results, and report a safe actionable error;
  cancelling an HTTP client does not guarantee a separate server stopped its
  computation. Test both supported OSes. Do not leak content through command
  lines, logs, exceptions or raw subprocess output.

## Tracing and evaluation exception

- Create a content-free, non-persisted local trace record for every question,
  including when Langfuse is unavailable or disabled. Record only an opaque
  operation ID, entered retrieval/drafting/verification stages, controlled
  status, elapsed time, and sanitized model/usage metadata when available.
  Export to Langfuse only when available and authorized. Never auto-capture
  model arguments, results, document text or exceptions; generic framework
  spans are excluded. No contentful CrewAI AMP traces or unapproved framework
  telemetry may bypass the authorized Langfuse route.
- Ordinary requests and all Feature 001 operations exclude questions,
  filenames, chunk IDs, document text and other previously prohibited data.
  For a specifically selected evaluation execution only, after disclosure of
  its question, destination and fields, require separate per-run confirmation
  of the question/source-ID fields, in addition to destination authorization.
  Allow only the question and verified eligible filenames/chunk IDs. Do not
  export text, content hashes, unrelated sources, credentials or raw
  exceptions. Selection and field confirmation grant no standing permission.
- Verify source eligibility by comparing the full ordered indexed chunks,
  IDs and page metadata with the known sample generated using the same
  ingestion configuration. A same-name private replacement fails. Recheck
  identity, content and authorization with dispatch under the existing
  serialization boundary. If a source fails verification omit its identifiers;
  if selection, per-run field confirmation, or destination authorization fails,
  omit all exceptional fields. Report a safe diagnostic if requested content
  export cannot proceed.
- Existing local confirmation, external destination authorization,
  revocation, route changes and outstanding dispatch rules are unchanged.
  Disabled, unavailable, failed, unconfirmed, and confirmed tracing remain
  distinguishable; no successful answer or failure is changed by a tracing
  problem. Mark delivery confirmed only on an explicit server acknowledgment
  tied to the trace. Queueing or an exception-free `flush()` is not proof; if
  the SDK cannot expose the acknowledgment, leave delivery unconfirmed.
  Detect observable exporter errors separately.

## Evaluation and offline verification

- Supply at least five redistributable non-sensitive cases with expected
  answer points and expected document sources: at least three answerable, one
  unanswerable, and one requiring multiple chunks or documents. The
  multi-source case must have at least two distinct expected points, each
  directly stated in a separate supporting chunk or document; it must not
  require inference across sources.
- Deterministic tests exercise answer/partial/abstention, fabricated and
  non-supporting citations, untrusted instructions, error distinctions, UI
  ownership, timeouts, revision races, trace isolation and evaluation
  eligibility. They make no real model or Langfuse calls.
- An opt-in local-model evaluation records, per case, expected-point coverage,
  every displayed claim and its cited-source correctness, abstention quality,
  missing points, relevant failures, and measured timing when available.
  Human review distinguishes retrieval and semantic errors; unavailable
  results stay unavailable. Do not claim unmeasured accuracy or generate the
  final evaluation report from this evaluator.
- Define the evaluator as an explicit command over the bundled case dataset;
  it must require opt-in confirmation, use the local model only, emit
  per-case observations, and not generate the final evaluation report.
- Emit exactly one JSONL object per case with `case_id`, `workflow_status`
  (`complete`, `partial`, `abstained`, `no_knowledge`, or `failed`),
  `expected_sources`, `expected_point_reviews` (each entry has `point` and
  `review_status`, one of `pending`, `covered`, `not_covered`, or `unavailable`),
  and `claims` (each entry has `text`, `citations` containing `filename` and
  `chunk_id`, `support_review` one of `pending`, `supported`, `unsupported`,
  `indeterminate`, or `unavailable`, and `citation_review` one of `pending`,
  `correct`, `incorrect`, or `unavailable`).
- `abstention_review` is one of `pending`, `appropriate`, `inappropriate`,
  `not_applicable`, or `unavailable`. `missing_points_review` is an object
  with `status` (`pending`, `reviewed`, or `unavailable`) and `points`; points
  are null while pending/unavailable and a list when reviewed, with an empty
  list meaning no missing points. `failure_code` is a safe code or null;
  `elapsed_ms` is a measured non-negative integer or null.
- The evaluator initializes human-review fields as pending and does not infer
  citation correctness, point coverage, abstention quality, or missing points.
  Reviewers save/update a local copy of the JSONL observations using the
  defined outcomes before treating those judgments as measured. `unavailable`
  is distinct from a negative review. Do not invent aggregate scores.
