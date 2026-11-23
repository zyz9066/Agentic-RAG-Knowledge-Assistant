"""Transactional local storage for committed knowledge and embeddings."""

import errno
import hashlib
import math
import os
import sqlite3
import struct
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class ReservationConflict(Exception):
    """A different indexing operation holds this filename."""


def _try_lock(file: BinaryIO) -> None:
    try:
        if os.name == "nt":
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise ReservationConflict("filename is already being indexed") from exc
        raise


def _unlock(file: BinaryIO) -> None:
    if os.name == "nt":
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    text: str
    embedding: tuple[float, ...]
    page: int | None


@dataclass(frozen=True, slots=True)
class StoredChunk:
    document_id: str
    filename: str
    chunk_id: str
    text: str
    embedding: tuple[float, ...]
    page: int | None


def _encode_embedding(vector: tuple[float, ...]) -> bytes:
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("embedding must contain finite values")
    try:
        encoded = struct.pack(f"<{len(vector)}f", *vector)
    except OverflowError as exc:
        raise ValueError("embedding cannot be represented as float32") from exc
    if not any(struct.unpack(f"<{len(vector)}f", encoded)):
        raise ValueError("embedding must have nonzero magnitude")
    return encoded


class SQLiteKnowledgeStore:
    """Keep document text and vectors in one transactional database."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS index_metadata (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    embedding_model_id TEXT NOT NULL,
                    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0)
                );
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL UNIQUE COLLATE BINARY,
                    indexed_at TEXT NOT NULL,
                    embedding_model_id TEXT NOT NULL,
                    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0)
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    document_id TEXT NOT NULL REFERENCES documents(document_id)
                        ON DELETE CASCADE,
                    chunk_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    page INTEGER,
                    PRIMARY KEY (document_id, chunk_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def reserve(self, filename: str) -> Iterator[None]:
        """Acquire a non-waiting process-lifetime lock for an exact filename."""
        if not filename:
            raise ValueError("filename is required")
        database_path = self.path.resolve()
        lock_dir = database_path.parent / (database_path.name + ".reservations")
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / hashlib.sha256(filename.encode("utf-8")).hexdigest()
        with lock_path.open("a+b") as lock_file:
            _try_lock(lock_file)
            try:
                yield
            finally:
                _unlock(lock_file)

    @staticmethod
    def _check_model(
        connection: sqlite3.Connection, model_id: str, dimension: int
    ) -> None:
        if not model_id or dimension <= 0:
            raise ValueError("embedding model and dimension are required")
        stored = connection.execute(
            "SELECT embedding_model_id, embedding_dimension FROM index_metadata WHERE id = 1"
        ).fetchone()
        if stored is not None and stored != (model_id, dimension):
            raise ValueError(
                "embedding model or dimension is incompatible with the index"
            )

    def replace(self, filename: str, model_id: str, chunks: list[Chunk]) -> None:
        """Publish a complete replacement or leave the prior document intact."""
        if not filename or not chunks:
            raise ValueError("filename and at least one chunk are required")
        dimension = len(chunks[0].embedding)
        if any(
            not chunk.chunk_id
            or not chunk.text.strip()
            or len(chunk.embedding) != dimension
            for chunk in chunks
        ):
            raise ValueError("invalid chunk or embedding dimension")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError("chunk identifiers must be unique")
        embeddings = [_encode_embedding(chunk.embedding) for chunk in chunks]

        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            with connection:
                self._check_model(connection, model_id, dimension)
                connection.execute(
                    "INSERT OR IGNORE INTO index_metadata VALUES (1, ?, ?)",
                    (model_id, dimension),
                )
                previous = connection.execute(
                    "SELECT document_id FROM documents WHERE filename = ?", (filename,)
                ).fetchone()
                document_id = previous[0] if previous is not None else uuid4().hex
                connection.execute(
                    """
                    INSERT INTO documents VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(filename) DO UPDATE SET
                        indexed_at = excluded.indexed_at,
                        embedding_model_id = excluded.embedding_model_id,
                        embedding_dimension = excluded.embedding_dimension
                    """,
                    (
                        document_id,
                        filename,
                        datetime.now(UTC).isoformat(),
                        model_id,
                        dimension,
                    ),
                )
                connection.execute(
                    "DELETE FROM chunks WHERE document_id = ?", (document_id,)
                )
                connection.executemany(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            document_id,
                            item.chunk_id,
                            position,
                            item.text,
                            vector,
                            item.page,
                        )
                        for position, (item, vector) in enumerate(
                            zip(chunks, embeddings)
                        )
                    ],
                )

    def read_chunks(self, model_id: str, dimension: int) -> list[StoredChunk]:
        """Read only committed chunks after verifying embedding compatibility."""
        with closing(self._connect()) as connection:
            self._check_model(connection, model_id, dimension)
            rows = connection.execute(
                """
                SELECT documents.document_id, documents.filename, chunks.chunk_id, chunks.text,
                       chunks.embedding, chunks.page
                FROM chunks JOIN documents USING (document_id)
                ORDER BY documents.filename COLLATE BINARY, chunks.position
                """
            ).fetchall()
        return [
            StoredChunk(
                document_id=document_id,
                filename=filename,
                chunk_id=chunk_id,
                text=text,
                embedding=struct.unpack(f"<{dimension}f", vector),
                page=page,
            )
            for document_id, filename, chunk_id, text, vector, page in rows
        ]
