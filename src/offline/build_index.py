#!/usr/bin/env python3
"""
Build a FAISS L2 index over a text file by chunking lines and embedding with OpenAI.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
from typing import Iterable, List, Sequence

import faiss
import numpy as np
from dotenv import load_dotenv
from tqdm import tqdm


CHUNK_SIZE_DEFAULT = 50
OVERLAP_DEFAULT = 10
WORKERS_DEFAULT = 16
MODEL_DEFAULT = "text-embedding-3-small"


def read_lines(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8") as infile:
        return [line.rstrip("\r\n") for line in infile]


def generate_chunks(
    lines: Sequence[str],
    chunk_size: int,
    overlap: int,
) -> List[dict]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    step = chunk_size - overlap
    chunks: List[dict] = []
    for chunk_id, start in enumerate(range(0, len(lines), step)):
        end = min(start + chunk_size, len(lines))
        if start >= end:
            break
        chunk_lines = lines[start:end]
        chunks.append(
            {
                "chunk_id": chunk_id,
                "start_line": start + 1,  # 1-based inclusive
                "end_line": end,  # 1-based inclusive
                "text": "\n".join(chunk_lines),
            }
        )
    return chunks


def _init_client():
    from openai import OpenAI

    return OpenAI()


_CLIENT = None


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = _init_client()
    return _CLIENT


def embed_text(text: str, model: str) -> List[float]:
    client = _get_client()
    response = client.embeddings.create(model=model, input=text)
    return response.data[0].embedding


def embed_chunks(
    chunks: Sequence[dict],
    model: str,
    workers: int,
) -> List[List[float]]:
    texts = [chunk["text"] for chunk in chunks]
    with ProcessPoolExecutor(max_workers=workers) as executor:
        func = partial(embed_text, model=model)
        embeddings = list(
            tqdm(
                executor.map(func, texts),
                total=len(texts),
                desc="Embedding chunks",
            )
        )
    return embeddings


def build_index(
    embeddings: np.ndarray,
) -> faiss.Index:
    if embeddings.ndim != 2:
        raise ValueError("Embeddings array must be 2D")
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index


def save_chunks(chunks: Sequence[dict], embeddings: Iterable[Sequence[float]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as outfile:
        for chunk, embedding in zip(chunks, embeddings):
            record = {
                **chunk,
                "embedding": [float(value) for value in embedding],
            }
            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")


def save_metadata(output_dir: Path, source_path: Path, chunks: Sequence[dict], chunk_size: int, overlap: int, model: str) -> None:
    metadata = {
        "source_path": str(source_path),
        "num_chunks": len(chunks),
        "chunk_size": chunk_size,
        "overlap": overlap,
        "model": model,
    }
    metadata_path = output_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as outfile:
        json.dump(metadata, outfile, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunk a text file and build a FAISS index using OpenAI embeddings.")
    parser.add_argument("--input-path", type=Path, default=Path("AI生产力训练营__text_only.csv"), help="Path to the input text file.")
    parser.add_argument("--output-dir", type=Path, default=Path("data"), help="Directory to store index and metadata.")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE_DEFAULT, help="Number of lines per chunk.")
    parser.add_argument("--overlap", type=int, default=OVERLAP_DEFAULT, help="Number of overlapping lines between chunks.")
    parser.add_argument("--workers", type=int, default=WORKERS_DEFAULT, help="Number of processes for embedding generation.")
    parser.add_argument("--model", type=str, default=MODEL_DEFAULT, help="OpenAI embedding model to use.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of chunks to embed (for testing).")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Please configure it in the environment or .env file.")

    lines = read_lines(args.input_path)
    chunks = generate_chunks(lines, args.chunk_size, args.overlap)
    if not chunks:
        raise RuntimeError("No chunks were generated. Check the input file and chunk configuration.")

    if args.limit is not None:
        chunks = chunks[: args.limit]

    embeddings_list = embed_chunks(chunks, args.model, args.workers)
    embeddings_array = np.asarray(embeddings_list, dtype="float32")

    index = build_index(embeddings_array)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.output_dir / "index.faiss"
    faiss.write_index(index, str(index_path))

    chunks_path = args.output_dir / "chunks.jsonl"
    save_chunks(chunks, embeddings_array, chunks_path)

    save_metadata(args.output_dir, args.input_path, chunks, args.chunk_size, args.overlap, args.model)

    print(f"Wrote FAISS index to {index_path}")
    print(f"Wrote chunk records to {chunks_path}")


if __name__ == "__main__":
    main()
