#!/usr/bin/env python3
"""Render the README's "games per rating bucket per speed" chart.

Reads the cached root-position payloads (one per speed × rating-bucket) and
writes `plots/lichess_population_by_speed.png`. Stylistically matches the
dark theme of the per-opening charts so the README looks consistent.

Run from the repo root:
    python generate_population_chart.py
"""

from __future__ import annotations

import json
import os
import sys

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from wickedlines import PLOT_ELO_BRACKETS
from wickedlines_stats import extract_wdb, totals

SPEEDS = [("blitz", "#57a8d8"), ("rapid", "#f07c32"), ("classical", "#c875c4")]
ROOT_FEN_SAFE = "rnbqkbnr_pppppppp_8_8_8_8_PPPPPPPP_RNBQKBNR w KQkq - 0 1"
CACHE_DIR = ".wickedlines_cache"
OUTPUT_PATH = os.path.join("plots", "lichess_population_by_speed.png")

# Match the per-opening plots' palette.
C = dict(bg="#121212", grid="#444", txt="#e9e9e9", cap="#c7c7c7")


def load_total(speed: str, bucket: str) -> int:
    path = os.path.join(CACHE_DIR, f"{ROOT_FEN_SAFE}__{speed}__{bucket}.json")
    with open(path) as f:
        return totals(extract_wdb(json.load(f)))


def format_count(n: float, _pos: int) -> str:
    """Y-axis tick formatter: 1.2M, 340K, 15K, etc."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.0f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return f"{int(n)}"


def bucket_label(bucket_str: str) -> str:
    """Render a Lichess bucket lower-bound as a human range, e.g. 1600 → 1600-1799."""
    val = int(bucket_str)
    if val == 0:
        return "<1000"
    if val == 2200:
        return "2200-2499"
    return f"{val}-{val + 199}"


def main() -> None:
    buckets = PLOT_ELO_BRACKETS
    centres = list(range(len(buckets)))

    # Verify every payload is on disk before drawing.
    missing = []
    counts = {speed: [] for speed, _ in SPEEDS}
    for speed, _ in SPEEDS:
        for bucket in buckets:
            try:
                counts[speed].append(load_total(speed, bucket))
            except FileNotFoundError as e:
                missing.append(str(e))
    if missing:
        print("Missing cache files for the root position:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        print("Run `python wickedlines.py plot e4 --speeds blitz,rapid,classical` once " "to seed the cache.", file=sys.stderr)
        sys.exit(1)

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=180, facecolor=C["bg"], constrained_layout=True)
    ax.set_facecolor(C["bg"])

    for speed, colour in SPEEDS:
        ys = counts[speed]
        ax.plot(centres, ys, marker="o", linewidth=2.4, markersize=8, color=colour, label=speed.capitalize())

    ax.set_yscale("log")
    ax.grid(True, ls=":", lw=0.7, color=C["grid"], which="both")
    for spine in ax.spines.values():
        spine.set_edgecolor(C["grid"])
    ax.tick_params(colors=C["txt"], labelsize=11)
    ax.set_xticks(centres)
    ax.set_xticklabels([bucket_label(b) for b in buckets], rotation=30, ha="right", color=C["txt"])
    ax.yaxis.set_major_formatter(FuncFormatter(format_count))

    ax.set_xlabel("Average rating of the two players (Lichess)", color=C["txt"], fontsize=13, labelpad=10)
    ax.set_ylabel("Games in the Lichess explorer (log scale)", color=C["txt"], fontsize=13, labelpad=10)
    ax.set_title(
        "Lichess opening explorer — game volume by speed and rating", color=C["txt"], fontsize=15, weight="bold", pad=14
    )

    leg = ax.legend(facecolor="#1c1c1c", edgecolor=C["grid"], fontsize=12, labelcolor=C["txt"], loc="lower left", frameon=True)
    leg.get_frame().set_linewidth(0.6)

    fig.text(
        0.5,
        -0.04,
        "Counts come from the root chess position. Same x-axis bucket = same average rating *within that speed's pool*.",
        color=C["cap"],
        fontsize=9,
        ha="center",
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
