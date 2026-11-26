# Quickstart and Validation: Knowledge Upload and Indexing

These commands and paths describe the implemented Feature 001 workflow.

## Prerequisites and setup

- Windows or Linux, Python 3.11-3.13, and `uv`.
- From the repository root, run `uv sync --locked` after `pyproject.toml` and
  `uv.lock` are created. Do not put credentials in the repository.
- The local embedding model may download on first use; prepare its configured
  cache in advance for offline use. The download fetches model files, not
  uploaded text. A missing model or failed download must produce a visible error.
- Text files must be UTF-8; an initial byte-order mark is removed, and a
  marker-only file is rejected. PDFs must be unencrypted and contain extractable
  text. Retrieval targets English. Other languages may be uploaded, but their
  retrieval quality is not guaranteed.

## Automated checks

From the repository root after implementation:

```powershell
uv run --locked ruff check app tests
uv run --locked ruff format --check app tests
uv run --locked pyright
uv run --locked pytest
```

The default test run uses deterministic embeddings, a recording trace
substitute, and temporary SQLite databases, with no live provider,
observability service, or model download. It covers trace privacy, consent,
and observability failures as specified in [the workflow contract](contracts/knowledge-workflow.md).
Run the separately documented opt-in real-model test with a preloaded cache to
check actual semantic retrieval. CI must exercise the declared Python/platform
matrix.

## Manual upload and retrieval

1. Start the app with `.\run.ps1`, which supplies the explicit loopback binding.
   Confirm the effective address is `127.0.0.1`; unsafe overrides must fail
   closed.
2. Upload original or public-domain text and PDF sample files containing known
   facts. Confirm the filename, progress, and success for each.
3. Submit an empty file, an unsupported file, a corrupt or no-text PDF, and a
   valid file in one within-limit batch. Confirm individual errors and the valid
   file's success. Test 10 and 11 files and 10 MiB and one byte over the limit.
   Also select a file above the widget transport limit, alone and with other
   files. Confirm the widget-level error, determine which entries actually reach
   the submitted batch, and correct and resubmit; do not expect an application
   result for a file the widget rejected before submission.
   For a file violating multiple validation rules, confirm that all applicable
   reasons are shown; an oversized batch is rejected for its count.
   Check clear per-file failures for undecodable text and encrypted PDFs,
   including an encrypted PDF that opens without a password.
4. Replace an indexed filename with different content. Verify only the new
   content is retrieved. Repeat with a deliberately failing replacement and
   verify that the previous content is still retrievable. While one attempt is
   in progress, submit the same filename from another session or process;
   verify rejection with a retry message, then retry after the first finishes.
   Confirm unrelated eligible files in the later batch still proceed.
5. Use `uv run --locked python -m app.retrieval_check --help` and run the local
   retrieval-check command against a known question.
   Verify the fact, source filename, and chunk identifier, then restart the app
   with the same knowledge location and compatible embedding configuration and
   verify them again. Use the known-evidence example in [the specification](spec.md).
   Returned candidates for unrelated questions do not establish relevance or
   answer sufficiency. Consult the command's `--help` for its arguments.
6. Confirm that external-provider tests require disclosure and new consent per
   batch and make zero document-text calls without consent. Feature 001 defaults
   to local embeddings; no production external provider is required.
7. Stop the application and follow the README's exact local knowledge-base
   removal procedure. Restart and confirm that the removed
   knowledge is no longer retrievable. This does not erase backups or remote
   copies.
8. Use a keyboard and screen reader to access the upload view and identify each
   filename's textual status and errors without relying on color.
9. Follow the implemented tracing setup. For the local exemption, confirm in
   the app that the receiving service and its delivery path stay on this
   computer without forwarding, proxies, tunnels, or redirects; the user is
   responsible for that service configuration. Confirm the application enforces
   a direct, verified loopback connection and requests confirmation again after
   restart. Report a known routing change and revoke confirmation before further
   local-exempt export. Alternatively, review the external destination and
   sanitized data and use the in-app controls to grant and revoke separate
   external-export permission. Exercise the disclosure, confirmation, permission
   state, and controls using keyboard and screen reader. Confirm intentionally
   disabled external export is shown as such, unavailable tracing is reported
   safely, and revocation or destination change discards unsent queued traces
   and stops new dispatches; already-started requests may finish and delivered
   data cannot be recalled.
   A live Langfuse inspection is opt-in and must use non-sensitive sample data;
   do not claim remote delivery without confirmation.

Keep the configured knowledge location on an unshared local location. The user
is responsible for system file sharing and other services that could expose it;
the application's local-only access restrictions do not control those services.

For behavior and evidence shapes, see [the workflow contract](contracts/knowledge-workflow.md)
and [data model](data-model.md).

## Validation record

The local offline suite passed with 90 tests and one opt-in real-model test
skipped. Ruff lint and formatting checks and Pyright passed on Windows 11 with
Python 3.13.18. The Windows/Linux Python matrix is configured in CI but has not
yet completed in GitHub Actions.

One local sample-corpus timing run indexed both sample files (748 input bytes,
two chunks) using the configured FastEmbed model. Model initialization,
including the first model-file download, took 5.929 seconds; indexing after
initialization took 0.112 seconds; one known-question retrieval took 0.010
seconds and returned the known observatory evidence. This single small-corpus
measurement is environment-specific and is not a performance target or a
retrieval-quality guarantee.

A subsequent CLI measurement of the `retrieval_check --help` startup took
1642.1 ms. A known-question retrieval took 2039.4 ms end to end and returned
`observatory.txt`, chunk `0`, with the text "The observatory is located in Larch
Valley." This additional process timing is environment-specific and does not
change the absence of a performance target or retrieval-quality guarantee.

The supported launcher was opened in a local browser at `127.0.0.1`; its
accessible page snapshot exposed the headings, upload region, file-upload
control, and submit button. Keyboard Tab navigation reached the file-upload and
submit controls. A subsequent browser smoke upload of `observatory.txt` reached
the Python application and completed with `indexed - File indexed.` Actual
browser boundary checks confirmed:

- A 10 MiB plus one-byte file reached Python and was rejected for exceeding
  10 MiB.
- Eleven submitted text files were all rejected count-first by the application.
- A 12 MiB file was rejected by the Streamlit widget with
  `File must be 11.0MB or smaller.` and was not submitted to Python.
- With one 12 MiB widget-rejected file and `observatory.txt` selected together,
  the valid file reached Python and indexed; the rejected file produced no
  application result.
- Reloading after a submitted batch cleared the submitted UI state and did not
  repeat the processing step.
- Keyboard Tab traversal reached the upload and submit controls. This automated
  browser check did not establish behavior with a physical screen reader.
