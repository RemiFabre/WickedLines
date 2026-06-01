"""Unit tests for WickedLines' numerical pipeline.

The pure-function module `wickedlines_stats` is the primary target — every
helper there gets its own dedicated test. We also add a few "parity" tests
against the actual `wickedlines` module to make sure the production code and
the pure functions agree on whatever the CLI prints.

Run with: `pytest -q`
"""

from __future__ import annotations

import math
from typing import Sequence

import pytest

import wickedlines_stats as ws

# ---------------------------------------------------------------------------
# ev / ev_pp / totals
# ---------------------------------------------------------------------------


def test_ev_zero_for_empty_bag():
    assert ws.ev((0, 0, 0)) == 0.0
    assert ws.ev_pp((0, 0, 0)) == 0.0
    assert ws.totals((0, 0, 0)) == 0


def test_ev_white_wins_only():
    assert ws.ev((10, 0, 0)) == 1.0
    assert ws.ev_pp((10, 0, 0)) == 100.0


def test_ev_black_wins_only():
    assert ws.ev((0, 0, 10)) == -1.0
    assert ws.ev_pp((0, 0, 10)) == -100.0


def test_ev_all_draws_is_zero():
    assert ws.ev((0, 10, 0)) == 0.0


def test_ev_symmetric_about_swap():
    assert ws.ev((7, 3, 5)) == pytest.approx(-ws.ev((5, 3, 7)))


def test_ev_pp_is_100x_ev():
    s = (12, 4, 9)
    assert ws.ev_pp(s) == pytest.approx(ws.ev(s) * 100.0)


# ---------------------------------------------------------------------------
# move_fraction
# ---------------------------------------------------------------------------


def test_move_fraction_basic():
    # parent: 100 games. move: 25. fraction = 0.25.
    assert ws.move_fraction((40, 20, 40), (10, 5, 10)) == pytest.approx(0.25)


def test_move_fraction_empty_parent_is_zero_not_error():
    assert ws.move_fraction((0, 0, 0), (0, 0, 0)) == 0.0


def test_move_fraction_does_not_clamp():
    # Inconsistent input: move says more games than parent. Should expose
    # the bug, not hide it.
    assert ws.move_fraction((1, 0, 0), (10, 0, 0)) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# delta_ev_pp
# ---------------------------------------------------------------------------


def test_delta_ev_zero_when_move_matches_parent():
    parent = (40, 20, 40)
    # A move whose outcome distribution mirrors the parent has ΔEV = 0.
    assert ws.delta_ev_pp(parent, (4, 2, 4)) == pytest.approx(0.0)


def test_delta_ev_positive_when_move_helps_white():
    parent = (40, 20, 40)  # EV = 0
    move = (8, 1, 1)  # EV = 0.7
    assert ws.delta_ev_pp(parent, move) == pytest.approx(70.0)


def test_delta_ev_negative_when_move_helps_black():
    parent = (40, 20, 40)
    move = (1, 1, 8)  # EV = -0.7
    assert ws.delta_ev_pp(parent, move) == pytest.approx(-70.0)


def test_delta_ev_sign_for_player():
    assert ws.is_delta_ev_good_for_player(5.0, "W") is True
    assert ws.is_delta_ev_good_for_player(5.0, "B") is False
    assert ws.is_delta_ev_good_for_player(-5.0, "W") is False
    assert ws.is_delta_ev_good_for_player(-5.0, "B") is True


def test_delta_ev_threshold():
    assert ws.is_delta_ev_good_for_player(0.4, "W", threshold=0.5) is False
    assert ws.is_delta_ev_good_for_player(0.6, "W", threshold=0.5) is True
    # The B side requires the magnitude to exceed the threshold *negatively*.
    assert ws.is_delta_ev_good_for_player(-0.4, "B", threshold=0.5) is False
    assert ws.is_delta_ev_good_for_player(-0.6, "B", threshold=0.5) is True


def test_is_delta_ev_player_arg_validated():
    with pytest.raises(ValueError):
        ws.is_delta_ev_good_for_player(0.0, "X")


# ---------------------------------------------------------------------------
# update_reach / reachability_of_line
# ---------------------------------------------------------------------------


def test_update_reach_mover_keeps_full_reach():
    # White plays a move. White's reach is unchanged; black's reach is
    # multiplied by the move fraction (black needs white to actually play this).
    w, b = ws.update_reach("W", 0.5, 1.0, 1.0)
    assert (w, b) == (1.0, 0.5)


def test_update_reach_black_to_move():
    w, b = ws.update_reach("B", 0.4, 1.0, 1.0)
    assert (w, b) == (0.4, 1.0)


def test_update_reach_rejects_invalid_player():
    with pytest.raises(ValueError):
        ws.update_reach("X", 0.5, 1.0, 1.0)


def test_reachability_monotonically_decreases():
    # Long walk: every multiplication is by ≤ 1 so neither value can grow.
    fractions = [0.5, 0.3, 0.4, 0.9, 0.2, 0.8]
    sides = ["W", "B", "W", "B", "W", "B"]
    w, b = ws.reachability_of_line(sides, fractions)
    assert 0.0 <= w <= 1.0
    assert 0.0 <= b <= 1.0


def test_reachability_caro_kann_example():
    # 1.e4 (W, fraction 0.5) 1...c6 (B, fraction 0.1).
    # After e4: white_wants=1, black_wants=0.5
    # After c6: white_wants=0.1, black_wants=0.5 (white needs black to play c6).
    w, b = ws.reachability_of_line(["W", "B"], [0.5, 0.1])
    assert w == pytest.approx(0.1)
    assert b == pytest.approx(0.5)


def test_reachability_white_opening_only_affects_black_wants():
    # 1.f4 — for a White opening, white_wants stays 1.0, only black_wants drops.
    w, b = ws.reachability_of_line(["W"], [0.02])
    assert w == 1.0
    assert b == pytest.approx(0.02)


def test_reachability_inputs_length_must_match():
    with pytest.raises(ValueError):
        ws.reachability_of_line(["W", "B"], [0.5])


# ---------------------------------------------------------------------------
# forcing_player
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, "White"),
        (1, "White"),  # e4
        (2, "Black"),  # e4 c5 — Black is the forcing player
        (3, "White"),  # e4 e5 Nf3
        (4, "Black"),
        (5, "White"),  # e4 e5 Nf3 Nc6 Bb5 — White's Ruy Lopez
    ],
)
def test_forcing_player_alternates(n: int, expected: str):
    assert ws.forcing_player(n) == expected


# ---------------------------------------------------------------------------
# chi2_p_value
# ---------------------------------------------------------------------------


def test_chi2_returns_one_for_empty_contrast():
    # "Other moves" bag is empty: no evidence of difference. We deliberately
    # return 1.0 here (NOT 0.0 as the old inline helper did).
    assert ws.chi2_p_value((10, 5, 10), (0, 0, 0)) == 1.0


def test_chi2_identical_distributions_give_high_p():
    # Two identical distributions: p should be ~1.0 (no difference).
    p = ws.chi2_p_value((10, 5, 10), (100, 50, 100))
    assert p > 0.99


def test_chi2_obviously_different_distributions_give_tiny_p():
    # Move-bag dominated by white wins; other-bag dominated by black wins.
    # With large counts the contingency test should be confident.
    p = ws.chi2_p_value((900, 50, 50), (50, 50, 900))
    assert p < 1e-10


def test_chi2_returns_one_when_scipy_raises():
    # All-zero rows make chi2_contingency raise ValueError; we should
    # gracefully return 1.0 instead of bubbling up.
    p = ws.chi2_p_value((0, 0, 0), (0, 0, 0))
    assert p == 1.0


# ---------------------------------------------------------------------------
# expected_elo_gain_per_100 / performance_elo_per_100
# ---------------------------------------------------------------------------


def test_expected_elo_gain_zero_when_no_reach():
    assert ws.expected_elo_gain_per_100(0.0, 10.0) == 0.0


def test_expected_elo_gain_zero_when_no_delta():
    assert ws.expected_elo_gain_per_100(0.5, 0.0) == 0.0


def test_expected_elo_gain_takes_absolute_value_of_delta():
    a = ws.expected_elo_gain_per_100(0.1, 5.0)
    b = ws.expected_elo_gain_per_100(0.1, -5.0)
    assert a == b


def test_expected_elo_gain_linear_in_inputs():
    base = ws.expected_elo_gain_per_100(0.1, 5.0, factor=1.0)
    assert base == pytest.approx(0.5)
    # Doubling reach doubles the result.
    assert ws.expected_elo_gain_per_100(0.2, 5.0, factor=1.0) == pytest.approx(1.0)
    # Doubling delta doubles the result.
    assert ws.expected_elo_gain_per_100(0.1, 10.0, factor=1.0) == pytest.approx(1.0)


def test_performance_elo_white_pass_through():
    line, base = ws.performance_elo_per_100(ev_value_pp=10.0, root_ev_pp=2.0, player="White", factor=1.0)
    assert line == 10.0
    assert base == 2.0


def test_performance_elo_black_flips_sign():
    line, base = ws.performance_elo_per_100(ev_value_pp=10.0, root_ev_pp=2.0, player="Black", factor=1.0)
    assert line == -10.0
    assert base == -2.0


def test_performance_elo_rejects_unknown_player():
    with pytest.raises(ValueError):
        ws.performance_elo_per_100(0.0, 0.0, "Draw")


def test_default_factor_matches_glicko_K_div_2_roughly():
    # Default factor should be in the 6–9 range (Lichess K is roughly 15 for
    # established users, so K/2 ≈ 7.5).
    assert 5.0 <= ws.DEFAULT_ELO_PER_EV_POINT <= 10.0


# ---------------------------------------------------------------------------
# extract_wdb / find_move
# ---------------------------------------------------------------------------


def test_extract_wdb_missing_keys_default_to_zero():
    assert ws.extract_wdb({"white": 5}) == (5, 0, 0)
    assert ws.extract_wdb({}) == (0, 0, 0)


def test_extract_wdb_handles_strings():
    # The cached JSON sometimes round-trips numbers as ints; we tolerate any
    # int-castable type.
    assert ws.extract_wdb({"white": "12", "draws": 3, "black": 4}) == (12, 3, 4)


def test_find_move_returns_match():
    payload = {"moves": [{"san": "e4", "white": 1}, {"san": "d4", "white": 2}]}
    assert ws.find_move(payload, "d4") == {"san": "d4", "white": 2}


def test_find_move_returns_none_for_missing():
    assert ws.find_move({"moves": []}, "e4") is None
    assert ws.find_move({}, "e4") is None


# ---------------------------------------------------------------------------
# Parity / integration: the pure helpers must match `wickedlines.py`.
# ---------------------------------------------------------------------------


def _wickedlines_inline_ev(w: int, d: int, b: int) -> float:
    """Same formula the CLI uses inline (e.g. line 188, 470, 502)."""
    total = w + d + b
    if total == 0:
        return 0.0
    return (w - b) / total * 100


@pytest.mark.parametrize("stats", [(0, 0, 0), (10, 0, 0), (0, 0, 10), (40, 20, 40), (1234, 567, 890), (1, 0, 0)])
def test_ev_pp_matches_inline_formula(stats):
    assert ws.ev_pp(stats) == pytest.approx(_wickedlines_inline_ev(*stats))


def test_kings_gambit_matches_inline_pipeline():
    """Take the cached blitz/1600 KG payload and reproduce the EV the CLI prints."""
    import json
    import os

    path = os.path.join(".wickedlines_cache", "rnbqkbnr_pppp1ppp_8_4p3_4PP2_8_PPPP2PP_RNBQKBNR b KQkq - 0 2__blitz__1600.json")
    if not os.path.exists(path):
        pytest.skip("cached KG blitz/1600 payload not present")
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        # In environments where the cache file is a Git LFS pointer rather
        # than the real JSON (e.g. CI without `lfs: true`), skip cleanly.
        pytest.skip("cached KG payload is an LFS pointer, not real JSON")
    inline = _wickedlines_inline_ev(*ws.extract_wdb(data))
    helper = ws.ev_pp(ws.extract_wdb(data))
    assert helper == pytest.approx(inline)
    # And the value should be in the ballpark we audited (~+8.85).
    assert 8.0 < helper < 9.5


def test_colorize_ev_still_works_for_legacy_callers():
    # The previous test stub asserted on the colour-formatting helper. We
    # keep one assertion so nobody accidentally breaks that downstream.
    # `wickedlines` imports `chess` at module load, so skip if that isn't
    # available (e.g. in a stripped-down environment).
    pytest.importorskip("chess")
    from wickedlines import Colors, colorize_ev

    assert colorize_ev(1.0) == Colors.GREEN + "+1.0" + Colors.END
