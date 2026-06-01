"""Pure statistical helpers used by WickedLines.

Everything here is a side-effect-free function on plain numbers (or, at most,
on the plain dicts returned by the Lichess opening explorer). They have no
chess, network, or filesystem dependencies and exist to make the math
testable in isolation from the CLI and the API client.

The intent is that the numbers produced by these helpers are byte-identical
to the numbers `wickedlines.py` already computes inline. Tests in
`wickedlines_test.py` lock that contract down.

Sign / orientation conventions used throughout:

- `(w, d, b)` are the (white wins, draws, black wins) counts from the
  perspective of the position's *outcome*, exactly as returned by the
  Lichess explorer.
- "EV" is `(w - b) / total`. Range `[-1, 1]`. Positive favours White.
- "EV (×100)" is the same thing multiplied by 100. Range `[-100, 100]`.
  This is what the CLI prints and what the plots use.
- "ΔEV" is EV in the ×100 scale and signed from White's perspective. A
  positive ΔEV means "white's outlook improved after this move". For
  Black-to-move positions, a *negative* ΔEV is what Black is hoping for.
- "Reachability" / `white_wants`, `black_wants` are cumulative probabilities
  in [0, 1] of getting the position on the board if that player is steering.
"""

from __future__ import annotations

from typing import Sequence, Tuple

# Lichess Glicko-2 K is about 15 for established players. Per-100-games Elo
# proxy is K * (W - L) / 2 ≈ 7.5 * EV(×100) / 100 = 0.075 * EV(×100). So the
# coefficient that converts "EV(×100)" to "expected Elo / 100 games against
# equally-rated opponents" is ~7.5. Used by both the plot's Performance
# chart and the hunt's ELO Gain metric.
DEFAULT_ELO_PER_EV_POINT = 7.5


# ---------------------------------------------------------------------------
# Position / move arithmetic
# ---------------------------------------------------------------------------


def totals(stats: Sequence[int]) -> int:
    """Sum of (w, d, b)."""
    w, d, b = stats
    return w + d + b


def ev(stats: Sequence[int]) -> float:
    """White-perspective expected value of a games bag, in [-1, 1].

    Returns 0.0 for an empty bag (rather than raising), matching the
    behaviour the CLI relies on for the "no games" edge case.
    """
    w, d, b = stats
    total = w + d + b
    if total == 0:
        return 0.0
    return (w - b) / total


def ev_pp(stats: Sequence[int]) -> float:
    """EV in the ×100 (`percentage points`) scale used by the CLI and plots."""
    return ev(stats) * 100.0


def move_fraction(parent_stats: Sequence[int], move_stats: Sequence[int]) -> float:
    """Fraction of the parent position's games that went through this move.

    0 when the parent is empty. Not clamped to [0, 1] on purpose — if the
    caller is passing inconsistent inputs we'd rather see a value > 1 in a
    test than silently truncate.
    """
    parent_total = totals(parent_stats)
    if parent_total == 0:
        return 0.0
    return totals(move_stats) / parent_total


def delta_ev_pp(parent_stats: Sequence[int], move_stats: Sequence[int]) -> float:
    """Change in white-perspective EV when going from `parent` to `move`, ×100.

    Mirrors `wickedlines.py`'s `delta_ev = (move_ev - pos_ev) * 100`.
    """
    return (ev(move_stats) - ev(parent_stats)) * 100.0


def is_delta_ev_good_for_player(delta_ev: float, player: str, threshold: float = 0.0) -> bool:
    """True if `delta_ev` (×100, White-perspective) helps `player`.

    `player` is "W"/"White" or "B"/"Black" (case-insensitive). The threshold
    is the absolute minimum |ΔEV| required to count as "good"; pass 0.0 if
    you only want the sign.
    """
    p = player.strip().lower()[:1]
    if p not in ("w", "b"):
        raise ValueError(f"player must be 'W' or 'B', got {player!r}")
    if p == "w":
        return delta_ev > threshold
    return delta_ev < -threshold


# ---------------------------------------------------------------------------
# Reachability accumulation
# ---------------------------------------------------------------------------


def update_reach(played_by: str, move_pct: float, white_wants: float, black_wants: float) -> Tuple[float, float]:
    """Update cumulative (white_wants, black_wants) after one ply.

    The mover always plays "their" move with probability 1, so the mover's
    cumulative reach is unchanged. The other side only sees this position if
    the mover actually chose this move, so the other side's reach is
    multiplied by `move_pct`.

    `played_by` is "W" or "B".
    """
    p = played_by.strip().upper()[:1]
    if p == "W":
        return white_wants, black_wants * move_pct
    if p == "B":
        return white_wants * move_pct, black_wants
    raise ValueError(f"played_by must be 'W' or 'B', got {played_by!r}")


def forcing_player(num_moves_played: int) -> str:
    """Which side made the last ply — returns 'White' or 'Black'.

    By convention WickedLines treats the side of the last opening move as
    "the player steering for this opening", so this is the side whose
    `*_wants` value is the one we plot as "Reachability".
    """
    if num_moves_played <= 0:
        # At the starting position there is no last mover; default to White
        # (matches the CLI's `if board.turn == chess.WHITE` fallback).
        return "White"
    return "White" if num_moves_played % 2 == 1 else "Black"


def reachability_of_line(moves_played_by: Sequence[str], move_fractions: Sequence[float]) -> Tuple[float, float]:
    """Walk a sequence of plies and return (white_wants, black_wants).

    `moves_played_by[i]` is "W" or "B"; `move_fractions[i]` is the fraction
    of the i-th ply's parent-position games that took that move. Both lists
    must have the same length.
    """
    if len(moves_played_by) != len(move_fractions):
        raise ValueError("moves_played_by and move_fractions must have the same length")
    white_wants, black_wants = 1.0, 1.0
    for played_by, pct in zip(moves_played_by, move_fractions):
        white_wants, black_wants = update_reach(played_by, pct, white_wants, black_wants)
    return white_wants, black_wants


# ---------------------------------------------------------------------------
# Significance test
# ---------------------------------------------------------------------------


def chi2_p_value(move_stats: Sequence[int], other_stats: Sequence[int]) -> float:
    """2×3 chi-square contingency p-value for "this move vs every other move".

    Returns `1.0` (no evidence of difference) when the contrast bag is empty
    or scipy refuses to compute — those are the only cases the caller can't
    reasonably do anything with. The CLI's original helper returned `0.0`
    for the empty case, which means "highly significant" and is semantically
    backwards; we deliberately deviate here, see `REVIEW_NOTES.md` finding
    B1. The hunt threshold logic then naturally ignores empty-contrast moves
    instead of treating them as significant.

    scipy.stats is imported lazily so this module stays importable in an
    environment that doesn't have scipy installed (the rest of the helpers
    don't need it).
    """
    if sum(other_stats) <= 0:
        return 1.0
    try:
        from scipy.stats import chi2_contingency  # type: ignore[import-not-found]
    except ImportError:
        return 1.0
    observed = [list(move_stats), list(other_stats)]
    try:
        _, p, _, _ = chi2_contingency(observed)
    except ValueError:
        return 1.0
    return float(p)


# ---------------------------------------------------------------------------
# Elo-proxy formulas
# ---------------------------------------------------------------------------


def expected_elo_gain_per_100(reach_prob: float, delta_ev: float, factor: float = DEFAULT_ELO_PER_EV_POINT) -> float:
    """Hunt mode's "Elo gain over 100 games" headline number.

    `reach_prob` is in [0, 1]; `delta_ev` is in the ×100 scale. The sign of
    `delta_ev` is ignored (the hunt only reports moves that are good for
    the mover, so the magnitude is what matters). Result is unitless "Elo".
    """
    return reach_prob * abs(delta_ev) * factor


def performance_elo_per_100(
    ev_value_pp: float, root_ev_pp: float, player: str, factor: float = DEFAULT_ELO_PER_EV_POINT
) -> Tuple[float, float]:
    """Plot mode's Performance chart values.

    Returns `(line_gain, baseline_gain)`. Both numbers are signed so a
    positive value means "good for the forcing player". For Black openings
    we flip the sign of both the line EV and the root EV.

    This wraps the inline `adj, base = (ev, root_ev) if player == "White"
    else (-ev, -root_ev); elo_gain.append(adj * ELO_FACTOR)` in
    wickedlines.py:530-533.
    """
    p = player.strip().lower()
    if p in ("white", "w"):
        return ev_value_pp * factor, root_ev_pp * factor
    if p in ("black", "b"):
        return -ev_value_pp * factor, -root_ev_pp * factor
    raise ValueError(f"player must be 'White' or 'Black', got {player!r}")


# ---------------------------------------------------------------------------
# Convenience accessors over Lichess explorer payloads
# ---------------------------------------------------------------------------


def extract_wdb(payload: dict) -> Tuple[int, int, int]:
    """`(white, draws, black)` from a Lichess explorer position payload."""
    return (int(payload.get("white", 0)), int(payload.get("draws", 0)), int(payload.get("black", 0)))


def find_move(payload: dict, san: str) -> dict | None:
    """Return the `moves[]` entry matching `san`, or None."""
    for m in payload.get("moves", []) or []:
        if m.get("san") == san:
            return m
    return None
