#!/usr/bin/env python3
"""List CSV chunks that still need an information_weight column."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def needs_weight(path: Path) -> bool:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                # Empty file — treat as needing work so it can be inspected.
                return True

            if "information_weight" not in header:
                return True

            weight_idx = header.index("information_weight")
            for row in reader:
                if len(row) <= weight_idx or not row[weight_idx].strip():
                    return True
    except Exception:
        # On parsing errors, request manual review by marking as unprocessed.
        return True

    return False


def collect_unprocessed(directory: Path) -> list[Path]:
    paths: list[Path] = []
    for file_path in sorted(directory.glob("*.csv")):
        if needs_weight(file_path):
            paths.append(file_path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path("data/chunks_1000_20"),
        help="Directory containing chunk CSV files",
    )
    parser.add_argument(
        "--relative",
        action="store_true",
        help="Print paths relative to the provided directory instead of the repo root",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional file path to write the list of unprocessed CSVs",
    )

    args = parser.parse_args()

    directory: Path = args.directory.resolve()
    if not directory.is_dir():
        raise SystemExit(f"Directory not found: {directory}")

    unprocessed = collect_unprocessed(directory)

    if args.relative:
        output_lines = [str(path.relative_to(directory)) for path in unprocessed]
    else:
        output_lines = [str(path) for path in unprocessed]

    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text("\n".join(output_lines), encoding="utf-8")

    for line in output_lines:
        print(line)


if __name__ == "__main__":
    main()
