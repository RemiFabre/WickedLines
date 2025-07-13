#!/usr/bin/env python3
import argparse
import json
import os
import re
import signal
import sys
import time
from collections import namedtuple
from datetime import datetime
from urllib.parse import quote

import chess
import chess.pgn
import requests
from scipy.stats import chi2_contingency
from tabulate import tabulate

# --- Configuration ---
HunterConfig = namedtuple(
    "HunterConfig",
    ["MIN_GAMES", "MIN_REACH_PCT", "DELTA_EV_THRESHOLD", "P_VALUE_THRESHOLD", "MAX_DEPTH", "BRANCH_FACTOR", "ELO_PER_POINT"],
)
DEFAULT_HUNTER_CONFIG = HunterConfig(
    MIN_GAMES=1000,
    MIN_REACH_PCT=1.0,
    DELTA_EV_THRESHOLD=5.0,
    P_VALUE_THRESHOLD=0.05,
    MAX_DEPTH=6,
    BRANCH_FACTOR=4,
    ELO_PER_POINT=8,
)
# Align with Lichess API enum
PLOT_ELO_BRACKETS = ["0", "1000", "1200", "1400", "1600", "1800", "2000", "2200", "2500"]

# Predefined list of openings for batch plotting
BATCH_OPENINGS = [
    # 1.e4 Openings
    {"name": "Sicilian Defense", "moves": "e4 c5"},
    {"name": "French Defense", "moves": "e4 e6"},
    {"name": "Caro-Kann Defense", "moves": "e4 c6"},
    {"name": "Scandinavian Defense", "moves": "e4 d5"},
    {"name": "Alekhine's Defense", "moves": "e4 Nf6"},
    {"name": "Modern Defense", "moves": "e4 g6"},
    {"name": "Italian Game", "moves": "e4 e5 Nf3 Nc6 Bc4"},
    {"name": "Ruy López", "moves": "e4 e5 Nf3 Nc6 Bb5"},
    {"name": "Vienna Game", "moves": "e4 e5 Nc3"},
    {"name": "Philidor Defense", "moves": "e4 e5 Nf3 d6"},
    {"name": "Pirc Defense", "moves": "e4 d6 d4 Nf6 Nc3 g6"},
    {"name": "Scotch Game", "moves": "e4 e5 Nf3 Nc6 d4"},
    {"name": "King's Gambit", "moves": "e4 e5 f4"},
    # 1.d4 Openings
    {"name": "Dutch Defense", "moves": "d4 f5"},
    {"name": "Queen's Gambit", "moves": "d4 d5 c4"},
    {"name": "Queen's Gambit Accepted", "moves": "d4 d5 c4 dxc4"},
    {"name": "Slav Defense", "moves": "d4 d5 c4 c6"},
    {"name": "London System", "moves": "d4 d5 Bf4"},
    {"name": "King's Indian Defense", "moves": "d4 Nf6 c4 g6"},
    {"name": "Nimzo-Indian Defense", "moves": "d4 Nf6 c4 e6 Nc3 Bb4"},
    {"name": "Grünfeld Defense", "moves": "d4 Nf6 c4 g6 Nc3 d5"},
    {"name": "Catalan Opening", "moves": "d4 Nf6 c4 e6 g3"},
    {"name": "Modern Benoni", "moves": "d4 Nf6 c4 c5 d5 e6"},
    # Other Openings
    {"name": "English Opening", "moves": "c4"},
    {"name": "Réti Opening", "moves": "Nf3 d5 c4"},
]

PLOT_COLORS = ["#57a8d8", "#f07c32", "#c875c4", "#4ecdc4", "#ffc300", "#c70039", "#aed581"]


# --- Global State & Classes ---
class Colors:
    GREEN, RED, BLUE, YELLOW, GRAY, END = ("\033[92m", "\033[91m", "\033[94m", "\033[93m", "\033[90m", "\033[0m")


class APIManager:
    def __init__(self):
        self.base_url = "https://explorer.lichess.ovh/lichess"
        self.cache = {}
        self.call_count = 0
        self.cache_dir = ".wickedlines_cache"
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_filepath(self, fen, speeds, ratings):
        safe_fen = fen.replace("/", "_")
        safe_key = f"{safe_fen}__{speeds}__{ratings}".replace(",", "_")
        return os.path.join(self.cache_dir, f"{safe_key}.json")

    def query(self, fen, speeds, ratings, force_refresh=False):
        cache_key = f"{fen}|{speeds}|{ratings}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        filepath = self._get_cache_filepath(fen, speeds, ratings)
        if not force_refresh and os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                self.cache[cache_key] = data
                return data
            except (json.JSONDecodeError, IOError) as e:
                print(f"\n{colorize(f'[WARN] Could not read cache file {os.path.basename(filepath)}: {e}', Colors.YELLOW)}")
        params = {"fen": fen, "variant": "standard", "speeds": speeds, "ratings": ratings}
        while True:
            self.call_count += 1
            try:
                r = requests.get(self.base_url, params=params)
                if r.status_code == 429:
                    print(f"\n{colorize('[INFO] Rate limit hit. Waiting 60s...', Colors.YELLOW)}")
                    time.sleep(60)
                    continue
                r.raise_for_status()
                data = r.json()
                try:
                    with open(filepath, "w") as f:
                        json.dump(data, f, indent=2)
                except IOError as e:
                    print(f"\n{colorize(f'[WARN] Could not write to cache file {filepath}: {e}', Colors.YELLOW)}")
                self.cache[cache_key] = data
                return data
            except requests.exceptions.RequestException as e:
                print(f"\n{colorize('[ERROR] API request failed: ' + str(e), Colors.RED)}")
                return None


api_manager = APIManager()
found_lines = []
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


# --- Helper Functions ---
def colorize(text, color):
    return f"{color}{text}{Colors.END}"


def strip_colors(text):
    return ANSI_ESCAPE_PATTERN.sub("", text)


def colorize_ev(ev):
    return colorize(f"{ev:+.1f}", Colors.GREEN if ev > 0.5 else Colors.RED if ev < -0.5 else Colors.END)


def get_fen_from_san_sequence(moves):
    board = chess.Board()
    try:
        for move in moves:
            board.push_san(move)
        return board.fen(), "W" if board.turn == chess.WHITE else "B"
    except Exception as e:
        print(f"{colorize('Error parsing move sequence: ' + str(e), Colors.RED)}")
        return None, None


def generate_lichess_url(moves):
    board, game = chess.Board(), chess.pgn.Game()
    node = game
    for move in moves:
        try:
            node = node.add_variation(board.push_san(move))
        except ValueError:
            return "Invalid move sequence"
    pgn = str(game).replace(" *", "")
    return f"https://lichess.org/analysis/pgn/{quote(pgn)}"


def calculate_p_value(move_stats, other_stats):
    observed = [list(move_stats), list(other_stats)]
    if sum(observed[1]) <= 0:
        return 0.0
    try:
        _, p, _, _ = chi2_contingency(observed)
        return p
    except ValueError:
        return 1.0


# --- "Line" Mode Logic ---
def print_line_reachability_stats(moves, speeds, ratings, interesting_move_san=None, force_refresh=False):
    headers = ["Move", "Played by", "Games", "p-value", "EV (×100)", "Raw %", "Move %", "If White Wants %", "If Black Wants %"]
    rows, board, white_wants, black_wants = [], chess.Board(), 1.0, 1.0
    root_data = api_manager.query(board.fen(), speeds, ratings, force_refresh=force_refresh)
    if not root_data or "white" not in root_data:
        return 0, 0, "W", [], ""
    root_total = sum(root_data.get(k, 0) for k in ["white", "draws", "black"])
    if root_total == 0:
        return 0, 0, "W", [], ""
    root_ev = (root_data.get("white", 0) - root_data.get("black", 0)) / root_total * 100 if root_total else 0
    rows.append(["(start)", "-", f"{root_total:,}", "-", colorize_ev(root_ev), "100.00", "100.00", "100.00", "100.00"])
    prev_data, line_name = root_data, (root_data.get("opening") or {}).get("name")
    for move_san in moves:
        played_by = "W" if board.turn == chess.WHITE else "B"
        move_data = next((m for m in prev_data.get("moves", []) if m.get("san") == move_san), None)
        if not move_data:
            break
        w, d, b = (move_data.get("white", 0), move_data.get("draws", 0), move_data.get("black", 0))
        parent_w, parent_d, parent_b = (prev_data.get("white", 0), prev_data.get("draws", 0), prev_data.get("black", 0))
        other_stats = (parent_w - w, parent_d - d, parent_b - b)
        p_value = calculate_p_value((w, d, b), other_stats)
        if p_value < 0.001:
            p_str = colorize("<0.001", Colors.GREEN)
        else:
            p_str = (
                colorize(f"{p_value:.3f}", Colors.GREEN)
                if p_value < DEFAULT_HUNTER_CONFIG.P_VALUE_THRESHOLD
                else f"{p_value:.3f}"
            )
        prev_total, move_total = parent_w + parent_d + parent_b, w + d + b
        move_pct = move_total / prev_total if prev_total > 0 else 0
        if played_by == "W":
            black_wants *= move_pct
        else:
            white_wants *= move_pct
        board.push_san(move_san)
        current_data = api_manager.query(board.fen(), speeds, ratings, force_refresh=force_refresh)
        if not current_data:
            break
        total = sum(current_data.get(k, 0) for k in ["white", "draws", "black"])
        if total == 0:
            break
        ev = (current_data.get("white", 0) - current_data.get("black", 0)) / total * 100 if total else 0
        move_str = move_san + (colorize(" <-- Interesting", Colors.BLUE) if move_san == interesting_move_san else "")
        rows.append(
            [
                move_str,
                played_by,
                f"{total:,}",
                p_str,
                colorize_ev(ev),
                f"{(total / root_total * 100):.2f}",
                f"{move_pct * 100:.2f}",
                f"{white_wants * 100:.2f}",
                f"{black_wants * 100:.2f}",
            ]
        )
        prev_data = current_data
        line_name = (current_data.get("opening") or {}).get("name")
    print(tabulate(rows, headers=headers, tablefmt="pretty"))
    return (white_wants * 100, black_wants * 100, "W" if board.turn == chess.WHITE else "B", moves, line_name)


def print_move_stats(fen, data, white_reach, black_reach, turn, move_list, p_val_thresh):
    player_str = "White" if turn == "W" else "Black"
    print(f"\nFinal Position (FEN): {fen}\nLichess URL: {generate_lichess_url(move_list)}")
    print(f"If White wants, this position will be reached {white_reach:.2f}% of the time.")
    print(f"If Black wants, this position will be reached {black_reach:.2f}% of the time.\n")
    pos_w, pos_d, pos_b = (data.get("white", 0), data.get("draws", 0), data.get("black", 0))
    pos_total = pos_w + pos_d + pos_b
    pos_ev = ((pos_w - pos_b) / pos_total) if pos_total else 0
    best_move_san = None
    if pos_total > 0:
        moves_with_stats = []
        for m in data.get("moves", []):
            total = sum(m.get(k, 0) for k in ["white", "draws", "black"])
            if total > 0:
                moves_with_stats.append({"san": m["san"], "ev": (m["white"] - m["black"]) / total})
        if moves_with_stats:
            best_move_san = (max if turn == "W" else min)(moves_with_stats, key=lambda x: x["ev"])["san"]
    headers, rows = ["Move", "Games", "EV", "ΔEV", "p-value", "Opening"], []
    for move in data.get("moves", []):
        w, d, b = move.get("white", 0), move.get("draws", 0), move.get("black", 0)
        total = w + d + b
        other_stats = (pos_w - w, pos_d - d, pos_b - b)
        if total == 0:
            continue
        move_ev = (w - b) / total if total > 0 else 0
        delta_ev = (move_ev - pos_ev) * 100
        p_value = calculate_p_value((w, d, b), other_stats)
        if p_value < 0.001:
            p_str = colorize("<0.001", Colors.GREEN)
        else:
            p_str = colorize(f"{p_value:.3f}", Colors.GREEN) if p_value < p_val_thresh else f"{p_value:.3f}"
        delta_ev_str = f"{delta_ev:+.1f}"
        if (turn == "W" and delta_ev > 0.5) or (turn == "B" and delta_ev < -0.5):
            delta_ev_str = colorize(delta_ev_str, Colors.GREEN)
        elif (turn == "W" and delta_ev < -0.5) or (turn == "B" and delta_ev > 0.5):
            delta_ev_str = colorize(delta_ev_str, Colors.RED)
        move_san_str = move.get("san", "?") + (colorize(" <-- Best", Colors.BLUE) if move.get("san") == best_move_san else "")
        opening_name = (move.get("opening") or {}).get("name", "-")
        rows.append([move_san_str, f"{total:,}", colorize_ev(move_ev * 100), delta_ev_str, p_str, opening_name])
    print(f"Next Move Statistics for {player_str}:")
    print(tabulate(rows, headers=headers, tablefmt="pretty"))


def run_line_mode(args):
    print(colorize(f"\nAnalyzing line: {' '.join(args.moves) or '(start)'}", Colors.YELLOW))
    print(f"Speeds: {args.speeds} | Ratings: {args.ratings}")
    interesting_move = getattr(args, "interesting_move_san", None)
    white_reach, black_reach, _, _, line_name = print_line_reachability_stats(
        args.moves, args.speeds, ratings=args.ratings, interesting_move_san=interesting_move, force_refresh=args.force_refresh
    )
    final_fen, final_turn = get_fen_from_san_sequence(args.moves)
    if not final_fen:
        return 1.0, 1.0, ""
    data = api_manager.query(final_fen, args.speeds, args.ratings, force_refresh=args.force_refresh)
    if data:
        print()
        print_move_stats(
            final_fen, data, white_reach, black_reach, final_turn, args.moves, DEFAULT_HUNTER_CONFIG.P_VALUE_THRESHOLD
        )
    return white_reach / 100, black_reach / 100, line_name


# --- "Hunt" Mode Logic ---
def find_interesting_lines_iterative(
    initial_board, initial_moves, start_white_prob, start_black_prob, speeds, ratings, config, max_finds, force_refresh=False
):
    stack = [(initial_board.fen(), initial_moves, None, start_white_prob, start_black_prob, len(initial_moves))]
    visited_nodes, found_count = 0, 0
    parent_board = chess.Board()
    if initial_moves:
        for move in initial_moves[:-1]:
            parent_board.push_san(move)
        stack[0] = (
            stack[0][:2] + (api_manager.query(parent_board.fen(), speeds, ratings, force_refresh=force_refresh),) + stack[0][3:]
        )
    else:
        stack[0] = (
            stack[0][:2]
            + (api_manager.query(initial_board.fen(), speeds, ratings, force_refresh=force_refresh),)
            + stack[0][3:]
        )

    while stack:
        if max_finds and found_count >= max_finds:
            print(colorize(f"\nReached max finds limit ({max_finds}). Halting.", Colors.YELLOW))
            break
        fen, move_history, prev_pos_data, white_prob, black_prob, depth = stack.pop()
        board = chess.Board(fen)
        visited_nodes += 1
        indent = "  " * (depth - len(initial_moves))
        print(
            f"\r{indent}{colorize(f'[{visited_nodes: >3}|{len(stack): >3}]', Colors.GRAY)} Searching:"
            f" {' '.join(move_history) or '(start)'}...",
            " " * 20,
            end="",
        )
        current_data = api_manager.query(fen, speeds, ratings, force_refresh=force_refresh)
        if not current_data:
            continue
        total_games = sum(current_data.get(k, 0) for k in ["white", "draws", "black"])
        is_white_turn = board.turn == chess.WHITE
        reach_prob = white_prob if is_white_turn else black_prob
        if total_games < config.MIN_GAMES or depth >= config.MAX_DEPTH or reach_prob * 100 < config.MIN_REACH_PCT:
            continue
        prev_total = sum(prev_pos_data.get(k, 0) for k in ["white", "draws", "black"])
        if prev_total == 0:
            continue
        pos_ev = (prev_pos_data.get("white", 0) - prev_pos_data.get("black", 0)) / prev_total if prev_total > 0 else 0
        parent_stats = (prev_pos_data.get("white", 0), prev_pos_data.get("draws", 0), prev_pos_data.get("black", 0))
        sorted_moves = sorted(
            current_data.get("moves", []), key=lambda m: sum(m.get(k, 0) for k in ["white", "draws", "black"]), reverse=True
        )
        for move_data in sorted_moves:
            w, d, b = (move_data.get("white", 0), move_data.get("draws", 0), move_data.get("black", 0))
            move_total = w + d + b
            if move_total < config.MIN_GAMES:
                continue
            other_stats = (parent_stats[0] - w, parent_stats[1] - d, parent_stats[2] - b)
            p_value = calculate_p_value((w, d, b), other_stats)
            if p_value >= config.P_VALUE_THRESHOLD:
                continue
            move_ev = (w - b) / move_total if move_total > 0 else 0
            delta_ev = (move_ev - pos_ev) * 100
            if abs(delta_ev) > config.DELTA_EV_THRESHOLD:
                if (is_white_turn and delta_ev > 0) or (not is_white_turn and delta_ev < 0):
                    found_count += 1
                    full_line_moves = move_history + [move_data["san"]]
                    player_name = "WHITE" if is_white_turn else "BLACK"
                    elo_gain = reach_prob * abs(delta_ev) * config.ELO_PER_POINT
                    opening_name = (move_data.get("opening") or {}).get("name", "no name")
                    report = {
                        "line_moves": full_line_moves,
                        "line_ev": move_ev * 100,
                        "delta_ev": delta_ev,
                        "p_value": p_value,
                        "elo_gain": elo_gain,
                        "opening_name": opening_name,
                        "player": player_name,
                        "reach_pct": reach_prob * 100,
                    }
                    found_lines.append(report)
                    title = (
                        f" FOUND OPPORTUNITY FOR {player_name} #{found_count} | ΔEV: {delta_ev:+.1f} | ELO Gain/100:"
                        f" {elo_gain:+.2f} "
                    )
                    print()
                    print(colorize("\n" + title.center(85, "="), Colors.BLUE))
                    run_line_mode(
                        argparse.Namespace(
                            moves=full_line_moves,
                            speeds=speeds,
                            ratings=ratings,
                            interesting_move_san=move_data["san"],
                            force_refresh=force_refresh,
                        )
                    )
                    print(colorize("=" * 85, Colors.BLUE) + "\n")
        for move_to_explore in reversed(sorted_moves[: config.BRANCH_FACTOR]):
            new_board = board.copy()
            new_board.push_san(move_to_explore["san"])
            move_pct = sum(move_to_explore.get(k, 0) for k in ["white", "draws", "black"]) / total_games if total_games else 0
            new_white_prob, new_black_prob = (
                (white_prob, black_prob * move_pct) if is_white_turn else (white_prob * move_pct, black_prob)
            )
            stack.append(
                (
                    new_board.fen(),
                    move_history + [move_to_explore["san"]],
                    current_data,
                    new_white_prob,
                    new_black_prob,
                    depth + 1,
                )
            )


def run_hunt_mode(args):
    global found_lines, interrupted_args, hunt_start_time, interrupted_line_name
    found_lines, interrupted_args = [], args
    config = DEFAULT_HUNTER_CONFIG
    hunt_start_time = time.time()
    print("--- WickedLines Blunder Hunt ---")
    print(
        f"Config: Min Games={config.MIN_GAMES}, Min Reach%={config.MIN_REACH_PCT}, ΔEV>|{config.DELTA_EV_THRESHOLD}|,"
        f" p<{config.P_VALUE_THRESHOLD}, Branch={config.BRANCH_FACTOR}, ELO Gain Factor={config.ELO_PER_POINT}"
    )
    board, start_white_prob, start_black_prob, line_name = chess.Board(), 1.0, 1.0, ""
    if args.moves:
        start_white_prob, start_black_prob, line_name = run_line_mode(
            argparse.Namespace(moves=args.moves, speeds=args.speeds, ratings=args.ratings, force_refresh=args.force_refresh)
        )
        for move in args.moves:
            try:
                board.push_san(move)
            except ValueError:
                return
    interrupted_line_name = line_name
    print(f"\n--- Starting Hunt from position: {' '.join(args.moves) or '(start)'} ---")
    find_interesting_lines_iterative(
        board,
        args.moves,
        start_white_prob,
        start_black_prob,
        args.speeds,
        args.ratings,
        config,
        args.max_finds,
        force_refresh=args.force_refresh,
    )
    hunt_duration = time.time() - hunt_start_time
    print(colorize("\n--- Hunt Complete ---", Colors.BLUE))
    if found_lines:
        print_final_summary(args, config, hunt_duration, line_name)
    print(f"Total API calls made: {api_manager.call_count} (many results were served from cache)")


# --- "Plot" and "Batch Plot" Mode Logic ---
def get_stats_for_line(moves, speed, rating_bracket, force_refresh=False):
    board = chess.Board()
    white_wants, black_wants = 1.0, 1.0
    line_name = "N/A"
    root_data = api_manager.query(board.fen(), speed, rating_bracket, force_refresh=force_refresh)
    if not root_data:
        return 0, 0, 0, 0, "API Error", "White"
    root_total_games = sum(root_data.get(k, 0) for k in ["white", "draws", "black"])
    if root_total_games == 0:
        root_total_games = 1

    root_ev = (root_data.get("white", 0) - root_data.get("black", 0)) / root_total_games * 100 if root_total_games > 0 else 0

    prev_data = root_data
    for move_san in moves:
        played_by = "W" if board.turn == chess.WHITE else "B"
        move_data = next((m for m in prev_data.get("moves", []) if m.get("san") == move_san), None)
        if not move_data:
            break
        parent_total_ply = sum(prev_data.get(k, 0) for k in ["white", "draws", "black"])
        if parent_total_ply == 0:
            break
        move_total = sum(move_data.get(k, 0) for k in ["white", "draws", "black"])
        move_pct = move_total / parent_total_ply if parent_total_ply > 0 else 0
        if played_by == "W":
            black_wants *= move_pct
        else:
            white_wants *= move_pct
        board.push_san(move_san)
        prev_data = api_manager.query(board.fen(), speed, rating_bracket, force_refresh=force_refresh)
        if not prev_data:
            break
        line_name = (prev_data.get("opening") or {}).get("name", line_name)
    is_last_move_by_white = len(moves) % 2 != 0
    forcing_player = "White" if is_last_move_by_white else "Black"
    reachability = white_wants if forcing_player == "White" else black_wants
    final_data = prev_data
    if not final_data:
        return 0, 0, 0, root_ev, line_name, forcing_player
    final_pos_total_games = sum(final_data.get(k, 0) for k in ["white", "draws", "black"])
    popularity = final_pos_total_games / root_total_games if root_total_games > 0 else 0
    if final_pos_total_games == 0:
        return (0, reachability * 100, popularity * 100, root_ev, line_name, forcing_player)
    ev = (
        (final_data.get("white", 0) - final_data.get("black", 0)) / final_pos_total_games * 100
        if final_pos_total_games > 0
        else 0
    )
    return ev, reachability * 100, popularity * 100, root_ev, line_name, forcing_player


def fetch_stats_for_lines(move_strings, speed, force_refresh=False):
    """
    Takes a list of move strings (e.g., ["e4 c5", "d4 d5"]) and returns
    a list of dictionaries, each containing the full stats for one line
    across all ELO brackets.
    """
    all_stats = []
    for move_str in move_strings:
        moves = move_str.split()
        print(colorize(f"\nFetching data for line: {move_str} ({speed})", Colors.YELLOW))

        elo_gain, base_gain, reach, pop, theory = [], [], [], [], []
        final_name, forcing_player = "Unknown Opening", "White"
        ELO_FACTOR = 6

        for bucket in PLOT_ELO_BRACKETS:
            ev, r_, p_, root_ev, name, player = get_stats_for_line(moves, speed, str(bucket), force_refresh=force_refresh)
            print(
                f"{colorize(f'  [{bucket:>4}]', Colors.GRAY)} EV: {colorize_ev(ev)} | Reach: {r_:.2f}% | Pop: {p_:.2f}% | Base"
                f" EV: {colorize_ev(root_ev)}"
            )
            adj, base = (ev, root_ev) if player == "White" else (-ev, -root_ev)
            elo_gain.append(adj * ELO_FACTOR)
            base_gain.append(base * ELO_FACTOR)
            reach.append(r_)
            pop.append(p_)
            theory.append(r_ / p_ if p_ else 0)
            forcing_player = player
            if name not in ("Unknown Opening", "N/A"):
                final_name = name

        all_stats.append(
            {
                "moves": moves,
                "move_string": move_str,
                "name": final_name,
                "forcing_player": forcing_player,
                "elo_gain": elo_gain,
                "base_gain": base_gain,
                "reach": reach,
                "pop": pop,
                "theory": theory,
            }
        )
    return all_stats


def generate_plots(stats_data, speed, outdir):
    """
    Core plotting engine. Generates 1080x1350 charts with a refined,
    professional layout for both single and dual-logo modes.
    """

    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib import patheffects as pe
    from scipy.interpolate import CubicSpline

    # --- LAYOUT TWEAKABLES & CONFIGURATION ---
    # This is the primary place to fine-tune the plot aesthetics.
    # 1. Default Logo Rectangles [left, bottom, width, height]
    # These are used for any opening NOT specified in LOGO_OVERRIDES.
    SINGLE_LOGO_RECT = [0.50, 0.15, 0.7, 0.7]
    DUAL_LOGO1_RECT = [-0.2, 0.0, 0.7, 0.7]  # Default for left logo
    DUAL_LOGO2_RECT = [0.5, 0.0, 0.7, 0.7]  # Default for right logo

    # 2. Per-Opening Logo Overrides
    # Add an entry here to give a specific opening a custom logo rectangle.
    # The key is the move string (e.g., "d4 d5 c4").
    # The value is the [left, bottom, width, height] rectangle.
    LOGO_OVERRIDES = {
        # Example: Make the Queen's Gambit logo bigger in single-plot mode
        "d4 d5 c4": {
            #  "single": [0.55, 0.20, 0.45, 0.7], # A custom rect for single view
            # "dual_1": [0.0, 0.15, 0.4, 0.6],   # Custom rect if it's the left logo
            # "dual_2": [0.6, 0.15, 0.4, 0.6],   # Custom rect if it's the right logo
        },
        "e4 e5 f4": {
            # This opening will use the default rectangles because it's not specified
        },
    }

    # 3. Text Positions
    SINGLE_TEXT_X = 0.05
    SINGLE_MAIN_TITLE_Y = 0.65
    SINGLE_SUB_TITLE_Y = 0.45
    SINGLE_CHART_TITLE_Y = 0.18
    DUAL_CHART_TITLE_Y = 0.12
    # --- END OF TWEAKABLES ---

    # Dynamically determine the plot mode ---
    plot_mode = "single"
    if len(stats_data) > 1:
        # Check if all move strings are the same. If so, we are comparing speeds.
        all_moves_same = len(set(s["move_string"] for s in stats_data)) == 1
        if all_moves_same:
            plot_mode = "compare_speeds"
        else:
            plot_mode = "compare_openings"

    # Determine output directory based on opening color
    color_folder = "white" if len(stats_data[0]["moves"]) % 2 != 0 else "black"

    # Smarter filename generation based on plot_mode ---
    if plot_mode == "compare_openings":
        # Classic comparison filename: opening1_vs_opening2_speed.png
        filename_prefix = "_vs_".join(s["move_string"].replace(" ", "_") for s in stats_data).lower() + f"_{speed}"
    else:  # Covers 'single' and 'compare_speeds'
        # New filename for single opening: opening_speed1_speed2.png
        moves_slug = stats_data[0]["move_string"].replace(" ", "_").lower()
        speeds_slug = speed.replace(",", "_").lower()
        filename_prefix = f"{moves_slug}_{speeds_slug}"

    # Create the final output path, e.g., "plots/black/e4_c5_rapid"
    outdir = os.path.join("plots", color_folder, filename_prefix)
    os.makedirs(outdir, exist_ok=True)

    buckets = [int(b) for b in PLOT_ELO_BRACKETS]
    centres = [(a + b) / 2 for a, b in zip(buckets[:-1], buckets[1:])] + [2600]
    tick_labels = [str(int(c)) if c != 2600 else "2500+" for c in centres]

    C = dict(bg="#121212", grid="#444", txt="#e9e9e9", cap="#c7c7c7", base="#b0b0b0", arrow="#efd545")
    charts = [
        {
            "title": "Performance",
            "key": "performance",
            "y_label": "Expected Elo gain per 100 games",
            "color": "#57a8d8",
            "data_key": "elo_gain",
        },
        {
            "title": "Reachability",
            "key": "reachability",
            "y_label": "Chance to reach position (%)",
            "color": "#f07c32",
            "data_key": "reach",
        },
        {
            "title": "Popularity",
            "key": "popularity",
            "y_label": "Overall popularity of line (%)",
            "color": "#c875c4",
            "data_key": "pop",
        },
        {
            "title": "Surprise",
            "key": "surprise",
            "y_label": "Surprise Factor (Reachability / Popularity)",
            "color": "#4ecdc4",
            "data_key": "theory",
        },
    ]

    def save(fig, tag, filename_prefix):
        filepath = os.path.join(outdir, f"{filename_prefix}_{tag}.png")
        fig.savefig(filepath, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.1)
        plt.close(fig)

    def header(ax_header, title, color):
        # Use the 'compare_openings' layout only for that specific mode
        if plot_mode == "compare_openings":
            ax_header.text(
                0.5, 0.95, "Chess Opening Statistics", color=C["cap"], fontsize=19, weight="semibold", ha="center", va="top"
            )
            line1_moves = stats_data[0]["move_string"]
            logo1_rect = LOGO_OVERRIDES.get(line1_moves, {}).get("dual_1", DUAL_LOGO1_RECT)
            logo1_path = f"./logos/{''.join(stats_data[0]['moves'])}_logo.png"
            if os.path.exists(logo1_path):
                box1 = ax_header.inset_axes(logo1_rect)
                box1.imshow(plt.imread(logo1_path))
                box1.axis("off")

            line2_moves = stats_data[1]["move_string"]
            logo2_rect = LOGO_OVERRIDES.get(line2_moves, {}).get("dual_2", DUAL_LOGO2_RECT)
            logo2_path = f"./logos/{''.join(stats_data[1]['moves'])}_logo.png"
            if os.path.exists(logo2_path):
                box2 = ax_header.inset_axes(logo2_rect)
                box2.imshow(plt.imread(logo2_path))
                box2.axis("off")

            ax_header.text(0.5, DUAL_CHART_TITLE_Y, title, color=color, fontsize=22, weight="bold", ha="center", va="center")
        else:  # Use the 'single' layout for both 'single' and 'compare_speeds' modes
            ax_header.text(
                SINGLE_TEXT_X,
                0.95,
                "Chess Opening Statistics",
                color=C["cap"],
                fontsize=19,
                weight="semibold",
                ha="left",
                va="top",
            )
            line_data = stats_data[0]
            ax_header.text(
                SINGLE_TEXT_X,
                SINGLE_MAIN_TITLE_Y,
                line_data["name"],
                color=C["txt"],
                fontsize=16,
                weight="bold",
                ha="left",
                va="center",
            )
            # Format the speed string nicely (e.g., "Blitz, Rapid, Classical")
            speeds_formatted = speed.replace(",", ", ").title()
            sub_title = f"({' '.join(line_data['moves'])}) — {speeds_formatted}"
            ax_header.text(
                SINGLE_TEXT_X,
                SINGLE_SUB_TITLE_Y,
                sub_title,
                color=C["txt"],
                fontsize=14,
                weight="semibold",
                ha="left",
                va="center",
            )
            ax_header.text(
                SINGLE_TEXT_X, SINGLE_CHART_TITLE_Y, title, color=color, fontsize=22, weight="bold", ha="left", va="center"
            )

            line_moves = line_data["move_string"]
            logo_rect = LOGO_OVERRIDES.get(line_moves, {}).get("single", SINGLE_LOGO_RECT)
            logo_path = f"./logos/{''.join(line_data['moves'])}_logo.png"
            if os.path.exists(logo_path):
                box = ax_header.inset_axes(logo_rect)
                box.imshow(plt.imread(logo_path))
                box.axis("off")

    def smooth(ax, xs, ys, col, label=None):
        cs = CubicSpline(xs, ys)
        dense = np.linspace(xs[0], xs[-1], 400)
        ax.plot(dense, cs(dense), color=col, lw=2.4, label=label)
        ax.plot(xs, ys, "o", ms=7, color=col)

    for chart_info in charts:
        fig = plt.figure(figsize=(6, 7.5), dpi=180, facecolor=C["bg"], constrained_layout=True)
        gs = fig.add_gridspec(2, 1, height_ratios=[0.25, 0.75])
        ax_header = fig.add_subplot(gs[0])
        ax_header.axis("off")
        ax_main = fig.add_subplot(gs[1])
        ax_main.set_facecolor(C["bg"])
        ax_main.grid(True, ls=":", lw=0.7, color=C["grid"])
        for s in ax_main.spines.values():
            s.set_edgecolor(C["grid"])
        ax_main.tick_params(colors=C["txt"], labelsize=13, pad=8)

        header(ax_header, chart_info["title"], chart_info["color"])
        ax_main.set_xlabel("Player rating (Lichess)", labelpad=15, color=C["txt"], fontsize=16)
        ax_main.set_xticks(centres)
        ax_main.set_xticklabels(tick_labels, rotation=45, ha="right", color=C["txt"])

        all_data = []
        for j, line_data in enumerate(stats_data):
            # Use different colors if we are comparing anything (speeds or openings)
            if plot_mode in ["compare_speeds", "compare_openings"]:
                color = PLOT_COLORS[j % len(PLOT_COLORS)]
            else:  # Single plot mode
                color = chart_info["color"]

            data = line_data[chart_info["data_key"]]
            all_data.extend(data)

            # Smarter legend label generation ---
            label = None
            if plot_mode == "compare_speeds":
                # Legend shows the speed: "Rapid", "Blitz", etc.
                label = line_data["speed"].capitalize()
            elif plot_mode == "compare_openings":
                # Legend shows the opening name and moves
                label = f"{line_data['name']} ({line_data['move_string']})"

            smooth(ax_main, centres, data, color, label=label)

        if chart_info["key"] == "performance":
            base_gain_data = stats_data[0]["base_gain"]
            all_data.extend(base_gain_data)
            base_label = f"Baseline (avg. {stats_data[0]['forcing_player']} perf.)"
            smooth(ax_main, centres, base_gain_data, C["base"], label=base_label)

        pad = (max(all_data) - min(all_data)) * 0.1 if all_data else 0.1
        ax_main.set_ylim(min(all_data) - pad - 0.1, max(all_data) + pad + 0.1)
        ax_main.text(
            0.02, 0.98, chart_info["y_label"], transform=ax_main.transAxes, color=C["txt"], fontsize=14, ha="left", va="top"
        )

        if chart_info["key"] == "performance":
            mid = len(centres) // 2
            ax_main.annotate(
                "above this line means better than average",
                xy=(centres[mid], base_gain_data[mid]),
                xytext=(centres[mid], ax_main.get_ylim()[0] + 0.45 * (ax_main.get_ylim()[1] - ax_main.get_ylim()[0])),
                arrowprops=dict(
                    arrowstyle="-|>", color=C["arrow"], lw=1.2, path_effects=[pe.withStroke(linewidth=3, foreground=C["bg"])]
                ),
                color=C["arrow"],
                fontsize=11,
                ha="center",
            )

        # Only show a legend if there's something to compare
        if plot_mode != "single":
            ax_main.legend(
                facecolor="#222", edgecolor="#555", fontsize=13, labelcolor=C["txt"], loc="lower left", fancybox=True
            )

        fig.supxlabel("Created with open source tool WickedLines, join the project!", color=C["cap"], fontsize=12)
        save(fig, chart_info["key"], filename_prefix)

    print(f"\nPNG files written to {outdir}")


def run_plot_mode(args):
    """Handler for the 'plot' command."""
    # Get the single move string for this plot run.
    move_string = " ".join(args.moves)

    # Parse the comma-separated speeds argument into a list of individual speeds.
    speeds_list = [s.strip() for s in args.speeds.split(",")]

    # This list will hold the full statistics for each speed.
    stats_data = []

    # Loop through each requested speed, fetch its data, and aggregate it.
    for speed in speeds_list:
        # fetch_stats_for_lines returns a list of dictionaries. Since we are
        # only fetching for one opening at a time here, we take the first element [0].
        line_data = fetch_stats_for_lines([move_string], speed, args.force_refresh)[0]

        # We tag the data with its speed. This allows the plotting function
        # to differentiate the lines in the legend when multiple speeds are plotted.
        line_data["speed"] = speed
        stats_data.append(line_data)

    # Generate a unique directory and filename prefix based on the moves and speeds.
    # e.g., "plots/e4_c5_blitz_rapid"
    moves_id = "_".join(args.moves).lower()
    speed_id = args.speeds.replace(",", "_").lower()
    outdir = os.path.join("plots", f"{moves_id}_{speed_id}")

    # Call the main plotting function. It can handle multiple data sets in stats_data.
    # We pass the original comma-separated string for potential use in titles.
    generate_plots(stats_data, args.speeds, outdir)


def run_compare_mode(args):
    """Handler for the 'compare' command."""
    stats_data = fetch_stats_for_lines(args.move_strings, args.speed, args.force_refresh)
    filename_prefix = "_vs_".join(s.replace(" ", "_") for s in args.move_strings).lower()
    speed_id = args.speed.lower()
    outdir = os.path.join("plots", f"{filename_prefix}_{speed_id}")
    generate_plots(stats_data, args.speed, outdir)


def run_batch_plot_mode(args):
    total_openings = len(BATCH_OPENINGS)
    print(colorize(f"Starting batch plot generation for {total_openings} openings...", Colors.YELLOW))
    print(f"Plots will be saved to the '{os.path.join(os.getcwd(), 'plots')}' directory.")

    for i, opening in enumerate(BATCH_OPENINGS):
        print(
            colorize(f"\n({i + 1}/{total_openings}) Generating plot for: {opening['name']} ({opening['moves']})", Colors.BLUE)
        )

        # We now pass the force_refresh argument from the main command down to the individual plot job.
        plot_args = argparse.Namespace(moves=opening["moves"].split(), speed=args.speed, force_refresh=args.force_refresh)

        try:
            run_plot_mode(plot_args)
            print(colorize(f"Successfully generated plot for {opening['name']}.", Colors.GREEN))
        except Exception as e:
            print(colorize(f"Failed to generate plot for {opening['name']}: {e}", Colors.RED))

        # No need to sleep if we are using cached data, but it's a good rate-limiting practice otherwise.
        if args.force_refresh:
            time.sleep(0.5)

    print(colorize("\nBatch plot generation complete.", Colors.YELLOW))


# --- Main Execution & Signal Handling ---
def generate_filename(args, config, line_name):
    line_slug = "_".join(args.moves) if args.moves else "start_pos"
    if line_name and line_name != "N/A":
        name_slug = "".join(c for c in line_name.split(":")[0] if c.isalnum() or c in " -").rstrip()
        line_slug = f"{line_slug}_{name_slug.replace(' ', '_')}"
    ratings_slug = f"ratings-{args.ratings.replace(',', '-')}"
    speeds_slug = f"speeds-{args.speeds.replace(',', '-')}"
    config_slug = f"MD-{config.MAX_DEPTH}_MG-{config.MIN_GAMES}_BF-{config.BRANCH_FACTOR}"
    return f"{line_slug}_{ratings_slug}_{speeds_slug}_{config_slug}.md"


def update_hunt_index(results_dir="hunt_results"):
    index_path = "HUNT_INDEX.md"
    try:
        if not os.path.exists(results_dir):
            return
        reports_data = []
        for filename in os.listdir(results_dir):
            if filename.endswith(".md"):
                parts = filename.replace(".md", "").split("_")
                data = {"path": os.path.join(results_dir, filename)}
                line_parts, config_parts = [], []
                config_started = False
                for part in parts:
                    if "ratings-" in part or "speeds-" in part or "MD-" in part:
                        config_started = True
                    if config_started:
                        config_parts.append(part)
                    else:
                        line_parts.append(part)
                data["line_slug"] = " ".join(line_parts)
                for part in config_parts:
                    if "ratings-" in part:
                        data["ratings"] = part.replace("ratings-", "").replace("-", ",")
                    if "speeds-" in part:
                        data["speeds"] = part.replace("speeds-", "").replace("-", ",")
                    if "MD-" in part:
                        data["config_str"] = part.replace("-", "=").replace("_", ", ")
                reports_data.append(data)
        grouped_reports = {}
        for report in reports_data:
            line = report.get("line_slug", "Unknown")
            if line not in grouped_reports:
                grouped_reports[line] = []
            grouped_reports[line].append(report)
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("# WickedLines Hunt Results Index\n\n")
            f.write("A collection of all opening opportunities discovered by the `hunt` command.\n\n")
            if not grouped_reports:
                f.write("*No reports found yet. Run a hunt to generate one!*")
            else:
                for line, reports in sorted(grouped_reports.items()):
                    f.write(f"## Hunt Reports for: `{line if line else 'Start Position'}`\n\n")
                    for report in reports:
                        f.write(
                            f"- **Ratings**: `{report.get('ratings', 'N/A')}` | **Speeds**: `{report.get('speeds', 'N/A')}` |"
                            f" **Config**: `{report.get('config_str', 'N/A')}` -> **[View Report]({report['path']})**\n"
                        )
                    f.write("\n")
        print(colorize(f"Updated master index file: {index_path}", Colors.YELLOW))
    except Exception as e:
        print(colorize(f"Could not update hunt index: {e}", Colors.RED))


def print_final_summary(args, config, hunt_duration, line_name):
    if not found_lines:
        return
    print(colorize("\n" + " Hunt Summary ".center(85, "-"), Colors.BLUE))
    print("Top opportunities ranked by expected ELO gain over 100 games:\n")
    file_output = [
        "# WickedLines Hunt Report",
        f"### For initial line: `{' '.join(args.moves) or '(start)'}` ({line_name or 'no name'})",
    ]
    file_output.append(f"\n- **Date:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    file_output.append(f"- **Ratings:** `{args.ratings}` | **Speeds:** `{args.speeds}`")
    file_output.append(
        f"- **Config:** Min Games=`{config.MIN_GAMES}`, Max Depth=`{config.MAX_DEPTH}`, Min Reach=`{config.MIN_REACH_PCT}%`,"
        f" Branch Factor=`{config.BRANCH_FACTOR}`"
    )
    file_output.append(f"- **Analysis Duration:** `{hunt_duration:.2f} seconds`")
    file_output.append(f"- **API Calls:** `{api_manager.call_count}`")
    file_output.append("\n---\n\nTop opportunities ranked by expected ELO gain over 100 games:\n")
    sorted_report = sorted(found_lines, key=lambda x: x["elo_gain"], reverse=True)
    for i, item in enumerate(sorted_report):
        rank = i + 1
        p_str = "<0.001" if item["p_value"] < 0.001 else f"{item['p_value']:.3f}"
        elo_gain_str = f"ELO Gain/100: {item['elo_gain']:>+5.2f}"
        player_title = item["player"].title()
        delta_ev_str = f"{colorize_ev(item['delta_ev'])} (good for {player_title})"
        delta_ev_str_plain = f"{item['delta_ev']:+.1f} (good for {player_title})"
        reach_pct_str = f"Reachable: {item['reach_pct']:.2f}%"
        opening_str = f"({colorize(item['opening_name'], Colors.GRAY)})"
        print(f"{rank}. {colorize(elo_gain_str, Colors.GREEN)} | {colorize(reach_pct_str, Colors.YELLOW)}")
        print(f"   Line: {colorize(' '.join(item['line_moves']), Colors.BLUE)} {opening_str}")
        print(f"   Impact: Line EV: {colorize_ev(item['line_ev']):<14} | ΔEV: {delta_ev_str}")
        print(f"   URL:  {generate_lichess_url(item['line_moves'])}")
        print("")
        file_output.append(f"## {rank}. ELO Gain/100: `{item['elo_gain']:+.2f}`")
        file_output.append(f"- **Line:** `{' '.join(item['line_moves'])}` ({item['opening_name']})")
        file_output.append(f"- **Reachable:** `{item['reach_pct']:.2f}%`")
        file_output.append(f"- **Impact:** Line EV: `{item['line_ev']:+.1f}`, ΔEV: `{delta_ev_str_plain}`")
        file_output.append(f"- **Significance (p-value):** `{p_str}`")
        file_output.append(f"- **[Analyze on Lichess]({generate_lichess_url(item['line_moves'])})**")
        file_output.append("\n---\n")
    results_dir = "hunt_results"
    filename = generate_filename(args, config, line_name)
    filepath = os.path.join(results_dir, filename)
    try:
        os.makedirs(results_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(file_output))
        print(colorize(f"Successfully saved hunt report to: {filepath}", Colors.YELLOW))
        update_hunt_index(results_dir)
    except Exception as e:
        print(colorize(f"Error saving report to file: {e}", Colors.RED))


def signal_handler(sig, frame):
    print(colorize("\n\nHunt interrupted by user.", Colors.YELLOW))
    if "hunt_start_time" in globals() and "interrupted_args" in globals() and found_lines:
        print_final_summary(interrupted_args, DEFAULT_HUNTER_CONFIG, time.time() - hunt_start_time, interrupted_line_name)
    print(f"\nTotal API calls made during this session: {api_manager.call_count}")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    global interrupted_args, hunt_start_time, interrupted_line_name, found_lines
    interrupted_args, hunt_start_time, interrupted_line_name = None, 0.0, ""
    found_lines = []

    parser = argparse.ArgumentParser(
        description="WickedLines: A tool for chess opening analysis using the Lichess database.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Available modes")

    parser_line = subparsers.add_parser("line", help="Analyze a single, specific line of moves.")
    parser_line.add_argument("moves", nargs="+", help="Move list in SAN (e.g., e4 e5 Nf3 Nc6)")
    parser_line.add_argument(
        "--speeds", default="blitz,rapid,classical", help="Comma-separated speed filters. Default: blitz,rapid,classical"
    )
    parser_line.add_argument(
        "--ratings",
        default="1600",
        help=(
            "Comma-separated rating buckets (enum: "
            "0,1000,1200,1400,1600,1800,2000,2200,2500). "
            "Each bucket covers its value up to the next (e.g. 1600 means 1600→1799). "
            "Default: 1600"
        ),
    )
    parser_line.add_argument(
        "--force-refresh", action="store_true", help="Ignore local cache and fetch fresh data from the API."
    )
    parser_line.set_defaults(func=run_line_mode)

    parser_hunt = subparsers.add_parser("hunt", help="Recursively search for interesting opportunities and blunders.")
    parser_hunt.add_argument("moves", nargs="*", help="Optional initial move sequence to start the hunt from.")
    parser_hunt.add_argument(
        "--speeds", default="blitz,rapid,classical", help="Comma-separated speed filters. Default: blitz,rapid,classical"
    )
    parser_hunt.add_argument(
        "--ratings",
        default="1600",
        help=(
            "Comma-separated rating buckets (enum: "
            "0,1000,1200,1400,1600,1800,2000,2200,2500). "
            "Each bucket covers its value up to the next (e.g. 1600 means 1600→1799). "
            "Default: 1600"
        ),
    )
    parser_hunt.add_argument("--max-finds", type=int, help="Stop the search after finding N interesting lines.")
    parser_hunt.add_argument(
        "--force-refresh", action="store_true", help="Ignore local cache and fetch fresh data from the API."
    )
    parser_hunt.set_defaults(func=run_hunt_mode)

    parser_plot = subparsers.add_parser("plot", help="Plot the performance of an opening across all ELO ratings.")
    parser_plot.add_argument("moves", nargs="+", help="Move list in SAN to plot (e.g., e4 c6).")
    parser_plot.add_argument(
        "--speeds",
        default="rapid",
        help="A single or comma-separated list of time controls for the plot (e.g., blitz,rapid). Default: rapid.",
    )
    parser_plot.add_argument(
        "--force-refresh", action="store_true", help="Ignore local cache and fetch fresh data from the API."
    )
    parser_plot.set_defaults(func=run_plot_mode)

    parser_compare = subparsers.add_parser("compare", help="Plot multiple openings on the same charts for comparison.")
    parser_compare.add_argument(
        "move_strings", nargs="+", help='Quoted, space-separated strings of moves to compare (e.g., "e4 c5" "d4 d5").'
    )
    parser_compare.add_argument(
        "--speed",
        default="rapid",
        choices=["blitz", "rapid", "classical"],
        help="A single, fixed time control for the plot. Default: rapid.",
    )
    parser_compare.add_argument(
        "--force-refresh", action="store_true", help="Ignore local cache and fetch fresh data from the API."
    )
    parser_compare.set_defaults(func=run_compare_mode)

    parser_batchplot = subparsers.add_parser("batchplot", help="Generate plots for a predefined list of major openings.")
    parser_batchplot.add_argument(
        "--speed",
        default="rapid",
        choices=["blitz", "rapid", "classical"],
        help="A single, fixed time control for all plots. Default: rapid.",
    )
    parser_batchplot.add_argument(
        "--force-refresh", action="store_true", help="Ignore local cache and fetch fresh data from the API."
    )
    parser_batchplot.set_defaults(func=run_batch_plot_mode)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
