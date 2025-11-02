#!/usr/bin/env python3
"""Compute sender-level statistics and generate visualizations for weighted chats."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Dict, List

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "Plotly is required for visualization. Install it via `uv pip install plotly`."
    ) from exc


def read_weighted_messages(path: Path) -> List[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [row for row in reader]
    if "information_weight" not in reader.fieldnames:
        raise ValueError("information_weight column missing in aggregated CSV")
    return rows


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


def render_dashboard(
    summary: List[dict[str, object]],
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

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            f"平均权重 Top {len(avg_top)}",
            f"平均权重 Bottom {len(avg_bottom)}",
            f"权重总和 Top {len(sum_top)}",
            f"权重总和 Bottom {len(sum_bottom)}",
        ),
        vertical_spacing=0.12,
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
        height=900,
        margin=dict(t=90, b=60, l=140, r=100),
    )

    # Top列表：从大到小显示；Bottom列表：从小到大显示
    fig.update_yaxes(autorange="reversed", showgrid=False, row=1, col=1)
    fig.update_yaxes(showgrid=False, autorange="reversed", row=1, col=2)
    fig.update_yaxes(autorange="reversed", showgrid=False, row=2, col=1)
    fig.update_yaxes(showgrid=False, autorange="reversed", row=2, col=2)

    fig.update_xaxes(range=[0, 1], row=1, col=1)
    fig.update_xaxes(range=[0, 1], row=1, col=2)

    fig.write_html(
        str(html_path),
        full_html=True,
        include_plotlyjs="cdn",
        include_mathjax=False,
    )


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

    args = parser.parse_args()

    rows = read_weighted_messages(args.input)
    summary = build_sender_summary(rows)
    write_summary_csv(summary, args.summary_output)
    render_dashboard(summary, args.html_output, args.top_k, args.min_messages)


if __name__ == "__main__":
    main()
