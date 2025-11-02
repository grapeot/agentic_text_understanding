#!/usr/bin/env python3
"""Split a CSV file into overlapping chunks with the header preserved."""

import argparse
import csv
import os
from pathlib import Path


def chunk_csv(
    input_path: Path,
    output_dir: Path,
    chunk_size: int,
    overlap: int,
) -> None:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open(newline="", encoding="utf-8") as infile:
        reader = csv.reader(infile)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("Input CSV is empty") from exc

        buffer = []
        chunk_index = 0

        def write_chunk(rows: list[list[str]]) -> None:
            nonlocal chunk_index
            if not rows:
                return
            chunk_path = output_dir / f"chunk_{chunk_index:04d}.csv"
            with chunk_path.open("w", newline="", encoding="utf-8") as outfile:
                writer = csv.writer(outfile)
                writer.writerow(header)
                writer.writerows(rows)
            chunk_index += 1

        for row in reader:
            buffer.append(row)
            if len(buffer) == chunk_size:
                write_chunk(buffer)
                buffer = buffer[-overlap:] if overlap else []

        if buffer and len(buffer) > overlap:
            write_chunk(buffer)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path, help="Path to the source CSV file")
    parser.add_argument("output_dir", type=Path, help="Destination directory for the chunks")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Number of rows per chunk (excluding header)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=20,
        help="Number of overlapping rows between consecutive chunks",
    )

    args = parser.parse_args()

    chunk_csv(args.input_csv, args.output_dir, args.chunk_size, args.overlap)


if __name__ == "__main__":
    main()
