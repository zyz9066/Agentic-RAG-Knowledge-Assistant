"""Retrieve local evidence from the command line for manual verification."""

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from app.config import AppConfig, load_config
from app.embeddings import EmbeddingError, LocalEmbeddings
from app.observability import (
    LangfuseTraceSink,
    TraceDiagnosticChannel,
    TracePermissionManager,
    WorkflowTracer,
)
from app.retrieval import (
    RetrievalError,
    get_diagnostics,
    new_operation_id,
    retrieve,
)
from app.storage import SQLiteKnowledgeStore


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve ranked local evidence with filename and chunk provenance."
    )
    parser.add_argument("question", help="Question used to retrieve evidence")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of evidence candidates to display (default: 5)",
    )
    return parser.parse_args(argv)


def _tracer(
    config: AppConfig, database: Path
) -> tuple[WorkflowTracer, TraceDiagnosticChannel]:
    diagnostics = TraceDiagnosticChannel()
    if config.trace_host is None:
        return WorkflowTracer(None, diagnostics), diagnostics
    permissions = TracePermissionManager(database, config.trace_host)
    sink = LangfuseTraceSink(
        permissions,
        diagnostics,
        public_key=config.trace_public_key,
        secret_key=config.trace_secret_key,
    )
    return WorkflowTracer(sink, diagnostics), diagnostics


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    try:
        config = load_config()
        database = config.knowledge_dir / "knowledge.sqlite3"
        store = SQLiteKnowledgeStore(database)
        tracer, trace_diagnostics = _tracer(config, database)
        operation_id = new_operation_id()
        provider = (
            LocalEmbeddings(config.embedding_model, config.model_cache_dir)
            if args.question.strip() and args.limit > 0
            else None
        )
    except ValueError as exc:
        print(f"Invalid application configuration: {exc}", file=sys.stderr)
        return 1
    except EmbeddingError:
        print(
            "The configured local embedding model is unavailable.",
            file=sys.stderr,
        )
        return 1
    except (OSError, sqlite3.Error):
        print("The local knowledge storage is unavailable.", file=sys.stderr)
        return 1

    try:
        evidence = retrieve(
            store,
            provider,
            args.question,
            args.limit,
            operation_id,
            tracer=tracer,
        )
    except RetrievalError as exc:
        print(f"Retrieval failed: {exc}", file=sys.stderr)
        for diagnostic in get_diagnostics(operation_id):
            print(diagnostic.message, file=sys.stderr)
        for diagnostic in trace_diagnostics.get(operation_id):
            print(diagnostic.message, file=sys.stderr)
        return 1

    print(json.dumps([asdict(item) for item in evidence], ensure_ascii=False))
    for diagnostic in trace_diagnostics.get(operation_id):
        print(diagnostic.message, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
