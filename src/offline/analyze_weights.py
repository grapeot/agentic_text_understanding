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
        summary.append(
            {
                "sender": sender,
                "message_count": data["count"],
                "average_weight": data["weight_sum"] / data["count"],
                "median_weight": statistics.median(weights),
                "max_weight": max(weights),
                "min_weight": min(weights),
            }
        )

    return summary


def write_summary_csv(summary: List[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sender",
        "message_count",
        "average_weight",
        "median_weight",
        "max_weight",
        "min_weight",
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

    sorted_summary = sorted(filtered, key=lambda x: x["average_weight"], reverse=True)
    top = sorted_summary[:top_k]
    bottom = list(reversed(sorted_summary[-top_k:])) if len(sorted_summary) >= top_k else list(reversed(sorted_summary))

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(f"Top {len(top)} Senders", f"Bottom {len(bottom)} Senders"),
    )

    fig.add_trace(
        go.Bar(
            x=[row["average_weight"] for row in top],
            y=[row["sender"] for row in top],
            text=[f"{row['message_count']} msgs" for row in top],
            orientation="h",
            marker=dict(color="#2E86DE"),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            x=[row["average_weight"] for row in bottom],
            y=[row["sender"] for row in bottom],
            text=[f"{row['message_count']} msgs" for row in bottom],
            orientation="h",
            marker=dict(color="#BFC9CA"),
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        template="plotly_white",
        title={
            "text": "Information Density by Sender",
            "x": 0.5,
            "font": {"size": 24, "family": "Helvetica, Arial, sans-serif"},
        },
        font=dict(family="Helvetica, Arial, sans-serif", size=14, color="#2C3E50"),
        bargap=0.2,
        height=600,
        margin=dict(t=80, b=50, l=120, r=80),
    )

    fig.update_yaxes(showgrid=False)
    fig.update_xaxes(range=[0, 1])

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
