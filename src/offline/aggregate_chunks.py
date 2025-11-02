#!/usr/bin/env python3
"""Combine weighted chunk CSVs back into a single file with averaged weights."""

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path
from typing import Iterable


CHUNK_PATTERN = re.compile(r"chunk_(\d{4})\.csv$")


def iter_chunk_files(directory: Path) -> Iterable[Path]:
    for path in sorted(directory.glob("chunk_*.csv")):
        match = CHUNK_PATTERN.search(path.name)
        if not match:
            continue
        yield path


def aggregate_weights(
    original_csv: Path,
    chunk_dir: Path,
    output_csv: Path,
    chunk_size: int,
    overlap: int,
) -> None:
    with original_csv.open(newline="", encoding="utf-8") as src:
        reader = csv.reader(src)
        header = next(reader)
        rows = list(reader)

    total_rows = len(rows)

    weight_sums = [0.0] * total_rows
    weight_counts = [0] * total_rows

    step = chunk_size - overlap
    if step <= 0:
        raise ValueError("chunk_size must be greater than overlap")

    for chunk_path in iter_chunk_files(chunk_dir):
        chunk_index = int(CHUNK_PATTERN.search(chunk_path.name).group(1))
        start_row = chunk_index * step

        with chunk_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            chunk_header = next(reader, None)

            if chunk_header is None:
                continue

            if "information_weight" not in chunk_header:
                continue

            weight_idx = chunk_header.index("information_weight")

            for offset, row in enumerate(reader):
                global_idx = start_row + offset
                if global_idx >= total_rows:
                    break
                if weight_idx >= len(row):
                    continue
                weight_text = row[weight_idx].strip()
                if not weight_text:
                    continue
                try:
                    weight_value = float(weight_text)
                except ValueError:
                    continue
                if math.isnan(weight_value):
                    continue
                weight_sums[global_idx] += weight_value
                weight_counts[global_idx] += 1

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.writer(dst)
        writer.writerow([*header, "information_weight"])
        for idx, base_row in enumerate(rows):
            if weight_counts[idx]:
                avg_weight = weight_sums[idx] / weight_counts[idx]
                weight_str = f"{avg_weight:.4f}".rstrip("0").rstrip(".")
            else:
                weight_str = ""
            writer.writerow([*base_row, weight_str])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--original",
        type=Path,
        default=Path("AI生产力训练营__text_only.csv"),
        help="Path to the source CSV used for chunking",
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("data/chunks_1000_20"),
        help="Directory containing processed chunk CSV files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/weighted_messages.csv"),
        help="Destination for the aggregated CSV",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Chunk size used during splitting",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=20,
        help="Overlap used between chunks",
    )

    args = parser.parse_args()

    aggregate_weights(
        args.original,
        args.chunks,
        args.output,
        args.chunk_size,
        args.overlap,
    )


if __name__ == "__main__":
    main()
