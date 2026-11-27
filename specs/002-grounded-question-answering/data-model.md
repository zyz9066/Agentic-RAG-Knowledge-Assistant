# Data Model: Evidence-Grounded Question Answering

These are design targets. Request, question, evidence, and answer values are
transient; no conversation history or document content is added to traces.

## Committed document revision

| Field | Rule |
|-------|------|
| `document_id`, `filename` | Preserve Feature 001 stable identity and exact-case unique label semantics. |
| `revision` | Opaque fresh identifier for every committed replacement, even identical content; unchanged on failed replacement. |
| ordered chunks | Same `chunk_id`, text, page and embedding semantics as Feature 001. |

An atomic migration gives every existing document a revision without changing
its content, IDs or embeddings. A replacement writes the new revision and
complete chunk set in the same transaction. Reads see only committed versions.
An interrupted or failed migration or replacement must not leave partial data.

## Question request and session job

`QuestionRequest` contains an opaque request ID, a nonblank question and
optional per-execution evaluation selection. The original question is
session-local, not an operation ID, filename, log field or ordinary trace field.

`SessionJob` associates one session and request ID with an owned worker and
state: `idle -> running -> answered | partial | abstained | no_knowledge |
failed`. Reject an overlapping submission with a wait message; do not queue it.
Terminal results are accepted only from the active request. Deadline,
interruption or worker error terminates it as failed; ignore late results and
release resources. No interaction automatically resubmits.

## Evidence snapshot and citation

An internal evidence record contains the unchanged public Feature 001 fields
`text`, exact `filename`, `chunk_id`, and `score`, plus `document_id`, opaque
`revision`, and a digest over exact chunk text. These are obtained together
from one committed snapshot before ranking. A digest is internal only; it is
neither an anonymized identifier nor trace metadata. Evidence and score are
candidates, not proof of relevance or support.

A citation identifies a retrieved evidence record by filename and chunk ID,
with internal revision and digest retained for checking. All citations in a
claim must resolve uniquely to retrieved snapshot records. Fabricated,
ambiguous, altered, or stale references are rejected.

## Draft, verification and outcome

A draft contains atomic claims and candidate citation keys. Verification
returns one unambiguous `supported`, `unsupported`, or `indeterminate`
decision per claim and its cited evidence. Structural validation rejects
malformed or inconsistent outcomes; semantic verification remains fallible.

An answer outcome is one of: complete supported answer, supported partial
answer plus missing/uncertain explanation, abstention, no knowledge, or safe
error. Each displayed factual claim has at least one valid supporting
citation. Never render raw draft text or unchecked verifier content as a
verified answer.

Before publication, and again upon subsequent app interaction/rerun, compare
every cited document revision and chunk digest against one fresh committed
snapshot. A changed or missing citation invalidates its whole claim; preserve
unaffected claims, warn and ask for resubmission. If no claim remains, show
the warning instead of the former answer. A failed check is a safe failure.
An idle view and a commit immediately after a check can be stale until the
next check; disclose this limitation.

## Evaluation case and source eligibility

An evaluation case contains a unique ID, non-sensitive question, category,
expected answer points and source documents, or an explicit absence of
support. At least five cases cover three answerable, one unanswerable and one
multi-source question. Cases can satisfy more than one category. The dataset
and original sample sources are repository-owned and redistributable.

Selection is an explicit, per-request user action after disclosure of the case,
destination and fields. It is not destination consent. An eligible source
must match a known source's full ordered indexed chunks and page/ID metadata,
computed from trusted sample material using the same ingestion configuration.
The source revision and eligibility are rechecked at dispatch. A filename
alone or a matched individual chunk is insufficient; unverifiable or unrelated
identifiers are omitted. Evaluation scores or review judgments are recorded
only when actually measured.

## Trace record and permissions

Each question has a content-free operation ID; entered stages include
retrieval, agent/task execution, verification, freshness check, and outcome,
with controlled status, non-negative elapsed time and sanitized available
model/usage fields. Only a selected eligible evaluation request may include
its disclosed question and eligible filenames/chunk IDs, after independent
destination authorization. No source text, digests, credentials or raw
exceptions are exported.

Existing destination-scoped external permission, process-lifetime local
confirmation, route invalidation, and dispatch/revocation serialization remain
in force. The eligibility check and permission check must use the same
serialized dispatch transaction so replacement cannot race the export start.
Trace diagnostics are separate from request outcomes; attempted or flushed
export is not proof of delivery.
