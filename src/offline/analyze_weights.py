#!/usr/bin/env python3
"""Compute sender-level statistics and generate visualizations for weighted chats."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "Plotly is required for visualization. Install it via `uv pip install plotly`."
    ) from exc


def read_weighted_messages(path: Path) -> Tuple[List[dict[str, str]], List[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [row for row in reader]
        fieldnames = reader.fieldnames or []
    if "information_weight" not in fieldnames:
        raise ValueError("information_weight column missing in aggregated CSV")
    return rows, fieldnames


def build_sender_summary(rows: List[dict[str, str]]) -> List[dict[str, object]]:
    stats: Dict[str, Dict[str, object]] = {}
    for row in rows:
        sender = row.get("sender_nickname", "") or "(unknown)"
        weight_text = (row.get("information_weight") or "").strip()
        if not weight_text:
            continue
        try:
            weight = float(weight_text)
        except ValueError:
            continue

        entry = stats.setdefault(
            sender,
            {
                "sender": sender,
                "count": 0,
                "weight_sum": 0.0,
                "weights": [],
            },
        )
        entry["count"] += 1
        entry["weight_sum"] += weight
        entry["weights"].append(weight)

    summary: List[dict[str, object]] = []
    for sender, data in stats.items():
        weights = data["weights"]
        if len(weights) >= 2:
            std_weight = statistics.pstdev(weights)
        else:
            std_weight = 0.0

        summary.append(
            {
                "sender": sender,
                "message_count": data["count"],
                "weight_sum": data["weight_sum"],
                "average_weight": data["weight_sum"] / data["count"],
                "median_weight": statistics.median(weights),
                "max_weight": max(weights),
                "min_weight": min(weights),
                "stddev_weight": std_weight,
            }
        )

    return summary


def write_summary_csv(summary: List[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sender",
        "message_count",
        "weight_sum",
        "average_weight",
        "median_weight",
        "max_weight",
        "min_weight",
        "stddev_weight",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary:
            writer.writerow(row)


def compute_distribution(rows: List[dict[str, str]]) -> List[Tuple[float, int]]:
    bucket_counts: Counter[float] = Counter()
    for row in rows:
        weight_text = (row.get("information_weight") or "").strip()
        if not weight_text:
            continue
        try:
            weight = float(weight_text)
        except ValueError:
            continue
        bucket = round(weight * 4) / 4
        bucket_counts[bucket] += 1
    return sorted(bucket_counts.items(), key=lambda x: x[0])


def render_dashboard(
    summary: List[dict[str, object]],
    rows: List[dict[str, str]],
    html_path: Path,
    top_k: int,
    min_messages: int,
) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)

    filtered = [row for row in summary if row["message_count"] >= min_messages]
    if not filtered:
        raise SystemExit("No senders meet the minimum message threshold for visualization.")

    def split_top_bottom(metric: str) -> tuple[List[dict[str, object]], List[dict[str, object]]]:
        sorted_desc = sorted(filtered, key=lambda x: x[metric], reverse=True)
        sorted_asc = list(reversed(sorted_desc))
        top = sorted_desc[:top_k]
        bottom = sorted_asc[:top_k]
        return top, bottom

    avg_top, avg_bottom = split_top_bottom("average_weight")
    sum_top, sum_bottom = split_top_bottom("weight_sum")
    distribution = compute_distribution(rows)

    fig = make_subplots(
        rows=3,
        cols=2,
        specs=[
            [{}, {}],
            [{}, {}],
            [{"colspan": 2}, None],
        ],
        subplot_titles=(
            f"平均权重 Top {len(avg_top)}",
            f"平均权重 Bottom {len(avg_bottom)}",
            f"权重总和 Top {len(sum_top)}",
            f"权重总和 Bottom {len(sum_bottom)}",
            "权重分布 (四分位)",
        ),
        vertical_spacing=0.13,
        horizontal_spacing=0.14,
    )

    def add_bar_trace(data: List[dict[str, object]], row: int, col: int, metric: str, color: str, show_error: bool = False) -> None:
        x_values = [row_data[metric] for row_data in data]
        y_values = [row_data["sender"] for row_data in data]
        text_values = [f"{row_data['message_count']} msgs" for row_data in data]
        trace_kwargs = dict(
            x=x_values,
            y=y_values,
            text=text_values,
            orientation="h",
            marker=dict(color=color),
        )
        if show_error:
            trace_kwargs["error_x"] = dict(
                type="data",
                array=[row_data["stddev_weight"] for row_data in data],
                visible=True,
            )
        fig.add_trace(go.Bar(**trace_kwargs), row=row, col=col)

    add_bar_trace(avg_top, 1, 1, "average_weight", "#2E86DE", show_error=True)
    add_bar_trace(avg_bottom, 1, 2, "average_weight", "#BFC9CA", show_error=True)
    add_bar_trace(sum_top, 2, 1, "weight_sum", "#27AE60")
    add_bar_trace(sum_bottom, 2, 2, "weight_sum", "#E59866")

    fig.update_layout(
        template="plotly_white",
        title={
            "text": "Information Density Breakdown",
            "x": 0.5,
            "font": {"size": 24, "family": "Helvetica, Arial, sans-serif"},
        },
        font=dict(family="Helvetica, Arial, sans-serif", size=14, color="#2C3E50"),
        bargap=0.18,
        height=1100,
        margin=dict(t=90, b=70, l=160, r=110),
    )

    # Top列表：从大到小显示；Bottom列表：从小到大显示
    fig.update_yaxes(autorange="reversed", showgrid=False, row=1, col=1)
    fig.update_yaxes(showgrid=False, autorange="reversed", row=1, col=2)
    fig.update_yaxes(autorange="reversed", showgrid=False, row=2, col=1)
    fig.update_yaxes(showgrid=False, autorange="reversed", row=2, col=2)

    fig.update_xaxes(range=[0, 1], row=1, col=1)
    fig.update_xaxes(range=[0, 1], row=1, col=2)

    if distribution:
        fig.add_trace(
            go.Bar(
                x=[f"{bucket:.2f}" for bucket, _ in distribution],
                y=[count for _, count in distribution],
                marker=dict(color="#8E44AD"),
            ),
            row=3,
            col=1,
        )
        fig.update_yaxes(title_text="消息条数", row=3, col=1)
        fig.update_xaxes(title_text="information_weight (四分位舍入)", row=3, col=1)

    fig.write_html(
        str(html_path),
        full_html=True,
        include_plotlyjs="cdn",
        include_mathjax=False,
    )


def filter_messages(
    rows: List[dict[str, str]],
    threshold: float,
) -> List[dict[str, str]]:
    filtered = []
    for row in rows:
        weight_text = (row.get("information_weight") or "").strip()
        if not weight_text:
            continue
        try:
            weight = float(weight_text)
        except ValueError:
            continue
        if weight > threshold:
            filtered.append(row)
    return filtered


def write_filtered_csv(
    rows: List[dict[str, str]],
    path: Path,
    fieldnames: List[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("results/weighted_messages.csv"),
        help="Aggregated CSV with information_weight column",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("results/sender_weight_summary.csv"),
        help="Destination CSV for sender-level statistics",
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        default=Path("results/information_weight_dashboard.html"),
        help="Output HTML for Plotly visualization",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of top/bottom senders to visualize",
    )
    parser.add_argument(
        "--min-messages",
        type=int,
        default=5,
        help="Minimum messages per sender to appear in the visualization",
    )
    parser.add_argument(
        "--filter-threshold",
        type=float,
        default=None,
        help="If set, drop messages with weight <= threshold and write to --filtered-output",
    )
    parser.add_argument(
        "--filtered-output",
        type=Path,
        default=None,
        help="Path for filtered CSV (only used when --filter-threshold is provided)",
    )

    args = parser.parse_args()

    rows, fieldnames = read_weighted_messages(args.input)
    summary = build_sender_summary(rows)
    write_summary_csv(summary, args.summary_output)
    render_dashboard(summary, rows, args.html_output, args.top_k, args.min_messages)

    if args.filter_threshold is not None:
        filtered_rows = filter_messages(rows, args.filter_threshold)
        output_path = (
            args.filtered_output
            if args.filtered_output is not None
            else Path("results/weighted_messages_filtered.csv")
        )
        write_filtered_csv(filtered_rows, output_path, fieldnames)

        original_lines = len(rows)
        filtered_lines = len(filtered_rows)
        original_bytes = args.input.stat().st_size if args.input.exists() else 0
        filtered_bytes = output_path.stat().st_size if output_path.exists() else 0

        reduction_pct = (
            (1 - filtered_lines / original_lines) * 100
            if original_lines
            else 0
        )
        print(
            "Filtered messages saved to",
            output_path,
            f"(>{args.filter_threshold} retained)",
        )
        print(
            f"Lines: {filtered_lines}/{original_lines} ({reduction_pct:.2f}% reduction)"
        )
        print(
            f"File size: {filtered_bytes} bytes (original {original_bytes} bytes)"
        )


if __name__ == "__main__":
    main()
