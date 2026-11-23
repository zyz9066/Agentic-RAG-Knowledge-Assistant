# Quickstart and Validation: Knowledge Upload and Indexing

These commands and paths describe the **planned implementation**, not files
that exist yet. Run them after `/speckit-implement` creates the application,
fixtures, tests, and dependency lock.

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
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv run --locked pytest
```

The default test run uses deterministic embeddings and temporary SQLite
databases, with no live provider or model download. Run the separately documented
opt-in real-model test with a preloaded cache to check actual semantic retrieval.
CI must exercise the declared Python/platform matrix.

## Manual upload and retrieval

1. Start the app using the documented supported launcher with its explicit
   loopback binding. Confirm the effective address is `127.0.0.1`; unsafe
   overrides must fail closed.
2. Upload original or public-domain text and PDF sample files containing known
   facts. Confirm the filename, progress, and success for each.
3. Submit an empty file, an unsupported file, a corrupt or no-text PDF, and a
   valid file in one within-limit batch. Confirm individual errors and the valid
   file's success. Test 10 and 11 files and 10 MiB and one byte over the limit.
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
5. Use the implemented local retrieval-check command against a known question.
   Verify the fact, source filename, and chunk identifier, then restart the app
   with the same knowledge location and compatible embedding configuration and
   verify them again. Use the known-evidence example in [the specification](spec.md).
   Returned candidates for unrelated questions do not establish relevance or
   answer sufficiency. Consult the command's `--help` for its arguments.
6. Confirm that external-provider tests require disclosure and new consent per
   batch and make zero document-text calls without consent. Feature 001 defaults
   to local embeddings; no production external provider is required.
7. Stop the application and follow the implemented README's exact local
   knowledge-base removal procedure. Restart and confirm that the removed
   knowledge is no longer retrievable. This does not erase backups or remote
   copies.
8. Use a keyboard and screen reader to access the upload view and identify each
   filename's textual status and errors without relying on color.

Keep the configured knowledge location on an unshared local location. The user
is responsible for system file sharing and other services that could expose it;
the application's local-only access restrictions do not control those services.

For behavior and evidence shapes, see [the workflow contract](contracts/knowledge-workflow.md)
and [data model](data-model.md).
