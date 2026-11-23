# Research: Knowledge Upload and Indexing

Research date: 2026-11-22. No application packages were installed and no
application runtime was executed in this planning phase.

## Storage and atomic replacement

**Decision**: SQLite stores document metadata, chunk text, and float32 vectors in
one database; the retrieval adapter computes exact cosine similarity.

**Rationale**: SQLite is a serverless local database with documented transactional
atomicity. One transaction can replace both chunks and their vectors and roll back
on errors; it avoids coordinating separate index and metadata stores. Exact
scanning is adequate for the specified small, single-user scope, not a claim of
scalability.

**Alternatives considered**: sqlite-vec adds an extension-loading and native-build
dependency; Chroma and LanceDB would need verified multi-operation replacement
semantics or an additional publication mechanism; FAISS alone needs separate
metadata persistence. Revisit an indexed vector store when corpus size warrants it.

Sources: [Python sqlite3](https://docs.python.org/3/library/sqlite3.html),
[SQLite atomic commit](https://www.sqlite.org/atomiccommit.html),
[SQLite foreign keys](https://www.sqlite.org/foreignkeys.html).

## Local embeddings

**Decision**: FastEmbed 0.9.1 with the CPU model `BAAI/bge-small-en-v1.5`
(384 dimensions); persist the model identifier and dimensionality with the index.

**Rationale**: ONNX-based local inference avoids sending document text to a
remote embedding service and avoids a PyTorch dependency. Model files may be
downloaded on first use; pin and document a separate model cache, verify offline
behavior, and never describe model setup as guaranteed offline. Record the
resolved model revision or file identity to detect embedding changes.
The [FastEmbed model list](https://qdrant.github.io/fastembed/examples/Supported_Models/)
lists a 512-token limit; chunk according to the actual tokenizer and account
for special tokens so embedding does not silently omit source text.

**Alternatives considered**: Sentence Transformers with PyTorch is heavier;
hosted embedding APIs add credentials and per-batch data-transfer consent.
Real-model evaluation is required to assess suitability; this model is primarily
for English, and no multilingual quality is assumed.

Sources: [FastEmbed](https://github.com/qdrant/fastembed),
[FastEmbed package](https://pypi.org/project/fastembed/).

## Parsing and UI

**Decision**: pypdf 7.1.1 for PDF text extraction and Streamlit 1.67.0 for the
local UI. Text files use UTF-8. Reject unreadable or no-extractable-text inputs;
OCR is outside this feature.

**Rationale**: pypdf is a lightweight pure-Python parser. Streamlit forms and
session state support explicit batch submission and reruns. File uploader type
filters are best-effort, not a security boundary: validate server-side. The
framework's own upload limit can reject very large files before application
validation. The user accepted a visible widget-level rejection before submission,
without an application per-entry outcome for that file. Set the transport limit
above 10 MiB so the exact boundary can be validated by the application, and
test real browser behavior, including other files selected alongside a rejected
one; the documentation does not establish that the app receives a rejected
file's name or metadata.
Ensure the supported launch sets loopback explicitly because command-line and
environment configuration can override project settings.

**Alternatives considered**: PyMuPDF has a different licensing profile and more
dependencies; OCR and a separate frontend are unnecessary for this feature.

Sources: [pypdf](https://pypdf.readthedocs.io/),
[file uploader](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader),
[forms](https://docs.streamlit.io/develop/concepts/architecture/forms),
[configuration precedence](https://docs.streamlit.io/develop/concepts/configuration/options).

## Dependency and test strategy

**Decision**: Use `pyproject.toml` plus `uv.lock`, pytest, Ruff, and Pyright.
Target Python 3.11-3.13 in CI on Windows and Linux. As of the research date,
PyPI metadata declares Streamlit 1.67.0 requires Python >=3.11, pypdf 7.1.1
requires >=3.10, and FastEmbed 0.9.1 requires >=3.10. `uv pip compile` with
`--only-binary :all:` resolved those exact runtime versions plus pytest, Ruff,
and Pyright independently for Python 3.11, 3.12, and 3.13 on x86-64 Windows and
Linux. These checks do not prove a single cross-platform lock can be generated,
or that the wheels install and run successfully.

**Rationale**: A checked-in lockfile makes environment resolution reproducible.
Use fakes for deterministic unit tests and real SQLite for transaction/restart
tests. Use an opt-in cached-model integration test for actual semantic retrieval.
CI must resolve, install, and exercise the selected matrix before support is
claimed; investigate wheel availability or conflicting transitive constraints
and revise the lock or supported range if necessary.

**Alternatives considered**: Unlocked requirements reduce reproducibility;
provider-only live tests are unreliable and expose data.

Sources: [Streamlit on PyPI](https://pypi.org/project/streamlit/),
[pypdf on PyPI](https://pypi.org/project/pypdf/),
[FastEmbed on PyPI](https://pypi.org/project/fastembed/),
[uv lock and sync](https://docs.astral.sh/uv/concepts/projects/sync/),
[Streamlit testing](https://docs.streamlit.io/develop/concepts/app-testing/get-started).

## Workflow observability

**Decision**: Plan Langfuse Python SDK 5.2.0 behind a small tracing interface,
with per-file indexing and retrieval traces and a deterministic offline
substitute. External trace export requires separate, revocable opt-in through
accessible in-app controls. Only an established end-to-end local destination
is exempt; a loopback proxy alone is not proof. Discard unsent queued traces
when permission is invalidated, while acknowledging in-flight dispatches may
complete. Dispatch coordination and destination classification remain
implementation and verification work, not demonstrated SDK behavior.

**Rationale**: The constitution requires workflow traces. Stable step names,
parent-child relationships, outcomes, and durations make failures diagnosable;
an allowlist avoids exporting document or question content. The SDK's automatic
input, output, and exception capture must not bypass that allowlist. As of the
research date, PyPI declares Python >=3.11 and <4 for SDK 5.2.0; resolution
alongside the other project dependencies and runtime compatibility remain
unverified.

**Alternatives considered**: Unconditional external export conflicts with the
user's opt-in choice; a live-only test strategy conflicts with deterministic
offline verification.

Sources: [Langfuse trace best practices](https://langfuse.com/docs/observability/best-practices),
[instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation),
[masking](https://langfuse.com/docs/observability/features/masking),
[Langfuse on PyPI](https://pypi.org/project/langfuse/).
