# Data Model: Evidence-Grounded Question Answering

These are design targets. Questions, evidence, answers, and local trace records
are transient. No conversation history or question/document content is
persisted.

## Committed document revision

| Field | Rule |
|---|---|
| `CommittedDocument.document_id` | Preserve Feature 001's stable document identity. |
| `CommittedDocument.filename` | Preserve the exact-case unique filename semantics. |
| `CommittedDocument.revision` | Opaque fresh identifier for every committed replacement, including identical content; unchanged on failed replacement. |
| `Chunk.chunk_id` | Non-empty and unique within a document; retain Feature 001 identity semantics. |
| `Chunk.text` | Non-empty extracted chunk text; preserve the existing chunking output. |
| `Chunk.page` | Integer page number or `None`, preserving Feature 001 extraction semantics. |
| `Chunk.embedding` | Finite, non-zero vector of the index's configured dimension; preserve the existing model/vector representation. |

An atomic migration gives every existing document a revision without changing
its content, IDs, or embeddings. A replacement writes the new revision and
complete chunk set in the same transaction. Reads see only committed versions.
An interrupted or failed migration or replacement must not leave partial data.

## Question request and session job

| Field | Rule |
|---|---|
| `QuestionRequest.request_id` | Opaque identifier unique to one explicit submission. |
| `QuestionRequest.question` | Required nonblank string; remains session-local and is not included in ordinary traces. |
| `QuestionRequest.evaluation_case_id` | Optional identifier for the explicitly selected, non-sensitive evaluation case. |
| `QuestionRequest.evaluation_fields_confirmed` | Per-request confirmation of the disclosed question and eligible source-ID fields; does not replace destination authorization. |
| `SessionJob.session_id` | Identifies the owning Streamlit session. |
| `SessionJob.request_id` | Associates the job with exactly one request. |
| `SessionJob.worker` | The owned worker; only the active request may publish its result. |
| `SessionJob.state` | `idle -> running -> answered | partial | abstained | no_knowledge | failed`; reject overlap, do not queue, ignore late results, and release owned resources at termination. |

No interaction automatically resubmits. Deadline, interruption, or worker
error terminates the active job as failed.

## Evidence snapshot and citation

| Field | Rule |
|---|---|
| `Evidence.text`, `Evidence.filename`, `Evidence.chunk_id`, `Evidence.score` | Preserve Feature 001's public retrieval shape and ranking semantics. |
| `EvidenceSnapshot.document_id`, `EvidenceSnapshot.revision` | Bind each retrieved candidate to the committed document version. |
| `EvidenceSnapshot.digest` | Digest of exact chunk text for internal freshness checks only; never export as trace metadata. |
| `Citation.filename`, `Citation.chunk_id` | Identify one retrieved evidence record using exact source identity. |
| `Citation.revision`, `Citation.digest` | Internal values retained to validate freshness; never displayed as source identifiers or exported. |

The versioned snapshot fields are read together from one committed database
snapshot before ranking. Evidence and similarity score are candidates, not
proof of relevance or support. Every citation must resolve uniquely to a
retrieved snapshot record; fabricated, ambiguous, altered, or stale references
are rejected.

## Draft, verification, and answer outcome

| Field | Rule |
|---|---|
| `Draft.atomic_claims` | Complete list of proposed factual claims; never render the raw draft. |
| `Draft.candidate_citation_keys` | References only to the retrieved evidence snapshot. |
| `ClaimVerification.claim_id` | Identifies the claim being checked. |
| `ClaimVerification.decision` | Exactly one of `supported`, `unsupported`, or `indeterminate` per claim. |
| `ClaimVerification.citation_keys` | Citations checked for the associated claim. |
| `AnswerOutcome.status` | Exactly one of `complete`, `partial`, `abstained`, `no_knowledge`, or `failed`. |
| `AnswerOutcome.supported_claims` | Only claims whose cited evidence directly states them; faithful paraphrase is allowed, but inference across passages is not. |
| `AnswerOutcome.missing_explanation` | Required when a partial or abstained answer needs to explain missing or uncertain information. |
| `AnswerOutcome.error_code` | Safe error category only; never a raw exception or sensitive payload. |

Unresolved contradictions in cited evidence make the affected claim
indeterminate. Each displayed factual claim has at least one valid supporting
citation. Structural validation rejects malformed or inconsistent outcomes;
semantic verification remains fallible. Never render unchecked verifier text.

Before publication, and again on each subsequent app rerun or state-changing
action (input edit, submission, navigation, keyboard/pointer activation),
compare every cited revision and chunk digest against one fresh committed
snapshot. Passive focus, hover, and scrolling do not trigger a check. A
changed or missing citation invalidates its whole claim; preserve unaffected
claims, warn, and ask for resubmission. A failed check is a safe failure. An
idle view and a commit immediately after a check can be stale until the next
required check; disclose this limitation.

## Evaluation case and source eligibility

| Field | Rule |
|---|---|
| `EvaluationCase.id` | Unique case identifier. |
| `EvaluationCase.question` | Non-sensitive, repository-owned, redistributable evaluation question. |
| `EvaluationCase.categories` | One or more of `answerable`, `unanswerable`, or `multi_source`; a case may satisfy multiple categories. A `multi_source` case has at least two distinct expected points, each directly stated in a separate supporting chunk or document; it does not require cross-source inference. |
| `EvaluationCase.expected_answer_points` | Expected factual points used for per-case review. |
| `EvaluationCase.expected_sources` | Expected source documents; empty only when `EvaluationCase.no_support` is true. |
| `EvaluationCase.no_support` | Explicitly identifies an unanswerable case with no supporting source. |

The dataset has at least five cases: three answerable, one unanswerable, and
one requiring multiple chunks or documents. Selection is an explicit,
per-request user action after disclosure of the case, destination, and fields.
It is not destination consent. Field-specific confirmation is separately
required for that request.

An eligible source must match a known source's full ordered indexed chunks and
page/ID metadata, computed from trusted sample material using the same
ingestion configuration. Recheck source revision and eligibility at dispatch.
A filename alone or a matched individual chunk is insufficient; omit
unverifiable or unrelated identifiers. Record evaluation scores or review
judgments only when actually measured.

## Trace record and permissions

| Field | Rule |
|---|---|
| `TraceRecord.operation_id` | Opaque ID; never derived from question text or source identity. |
| `TraceRecord.stages` | Only entered stages, including retrieval, agent/task execution, verification, freshness check, and outcome. |
| `TraceStage.name`, `TraceStage.status` | Controlled stage name and status. |
| `TraceStage.elapsed_ms` | Non-negative elapsed time for an entered stage. |
| `TraceStage.model_id`, `TraceStage.usage_details` | Sanitized values only when available; never fabricate missing metadata. |
| `TraceRecord.export_status` | `disabled`, `unavailable`, `failed`, `unconfirmed`, or `confirmed`; `confirmed` requires an explicit server acknowledgment tied to the trace. Queueing or flushing alone leaves the status `unconfirmed`. |
| `EvaluationTracePayload.question` | May be exported only for an explicitly selected eligible case with per-run field confirmation and destination authorization. |
| `EvaluationTracePayload.source_ids` | Only verified eligible filenames and chunk IDs; never document text or digests. |

Create a content-free `TraceRecord` for every request and retain it only for
the session; do not persist it. Langfuse export is attempted only when
available and authorized. Evaluation payload fields require all independent
gates: selected case, per-run field confirmation, verified source eligibility,
and destination authorization. No source text, credentials, or raw exceptions
are exported.

Existing destination-scoped external permission, process-lifetime local
confirmation, route invalidation, and dispatch/revocation serialization remain
in force. The eligibility check and permission check use the same serialized
dispatch transaction so replacement cannot race export. Trace diagnostics are separate from request outcomes; attempted, queued, or
flushed export is not proof of delivery. Mark an export `confirmed` only after
an explicit server acknowledgment tied to that trace. If the SDK cannot expose
that acknowledgment, retain `unconfirmed`; detected exporter errors are
`failed`, while disabled and unavailable remain distinct.
