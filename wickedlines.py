#!/usr/bin/env python3
import chess
import chess.pgn
import requests
import time
import argparse
import signal
import sys
import os
import re
from urllib.parse import quote
from tabulate import tabulate
from collections import namedtuple, deque
from scipy.stats import chi2_contingency
from datetime import datetime

# --- Matplotlib Dependency ---
try:
    import matplotlib.pyplot as plt
except ImportError:
    print("Matplotlib not found. Please install it with: pip install matplotlib")
    sys.exit(1)

# --- Configuration ---
HunterConfig = namedtuple('HunterConfig', ['MIN_GAMES', 'MIN_REACH_PCT', 'DELTA_EV_THRESHOLD', 'P_VALUE_THRESHOLD', 'MAX_DEPTH', 'BRANCH_FACTOR', 'ELO_PER_POINT'])
DEFAULT_HUNTER_CONFIG = HunterConfig(MIN_GAMES=1000, MIN_REACH_PCT=1.0, DELTA_EV_THRESHOLD=5.0, P_VALUE_THRESHOLD=0.05, MAX_DEPTH=6, BRANCH_FACTOR=4, ELO_PER_POINT=8)
PLOT_ELO_BRACKETS = ["400", "600", "800", "1000", "1200", "1400", "1600", "1800", "2000", "2200", "2500"]

# Predefined list of openings for batch plotting
BATCH_OPENINGS = [
    # 1.e4 Openings
    {'name': 'Sicilian Defense', 'moves': 'e4 c5'},
    {'name': 'French Defense', 'moves': 'e4 e6'},
    {'name': 'Caro-Kann Defense', 'moves': 'e4 c6'},
    {'name': 'Scandinavian Defense', 'moves': 'e4 d5'},
    {'name': "Alekhine's Defense", 'moves': 'e4 Nf6'},
    {'name': 'Modern Defense', 'moves': 'e4 g6'},
    {'name': 'Italian Game', 'moves': 'e4 e5 Nf3 Nc6 Bc4'},
    {'name': 'Ruy López', 'moves': 'e4 e5 Nf3 Nc6 Bb5'},
    {'name': 'Vienna Game', 'moves': 'e4 e5 Nc3'},
    {'name': 'Philidor Defense', 'moves': 'e4 e5 Nf3 d6'},
    {'name': 'Pirc Defense', 'moves': 'e4 d6 d4 Nf6 Nc3 g6'},
    {'name': 'Scotch Game', 'moves': 'e4 e5 Nf3 Nc6 d4'},
    {'name': "King's Gambit", 'moves': 'e4 e5 f4'},
    # 1.d4 Openings
    {'name': 'Dutch Defense', 'moves': 'd4 f5'},
    {'name': "Queen's Gambit", 'moves': 'd4 d5 c4'},
    {'name': "Queen's Gambit Accepted", 'moves': 'd4 d5 c4 dxc4'},
    {'name': 'Slav Defense', 'moves': 'd4 d5 c4 c6'},
    {'name': 'London System', 'moves': 'd4 d5 Bf4'},
    {'name': "King's Indian Defense", 'moves': 'd4 Nf6 c4 g6'},
    {'name': 'Nimzo-Indian Defense', 'moves': 'd4 Nf6 c4 e6 Nc3 Bb4'},
    {'name': 'Grünfeld Defense', 'moves': 'd4 Nf6 c4 g6 Nc3 d5'},
    {'name': 'Catalan Opening', 'moves': 'd4 Nf6 c4 e6 g3'},
    {'name': 'Modern Benoni', 'moves': 'd4 Nf6 c4 c5 d5 e6'},
    # Other Openings
    {'name': 'English Opening', 'moves': 'c4'},
    {'name': 'Réti Opening', 'moves': 'Nf3 d5 c4'},
]


# --- Global State & Classes ---
class Colors:
    GREEN, RED, BLUE, YELLOW, GRAY, END = '\033[92m', '\033[91m', '\033[94m', '\033[93m', '\033[90m', '\033[0m'

class APIManager:
    def __init__(self):
        self.base_url = "https://explorer.lichess.ovh/lichess"
        self.cache = {}
        self.call_count = 0
    def query(self, fen, speeds, ratings):
        cache_key = f"{fen}|{speeds}|{ratings}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        params = {"fen": fen, "variant": "standard", "speeds": speeds, "ratings": ratings}
        while True:
            self.call_count += 1
            try:
                r = requests.get(self.base_url, params=params)
                if r.status_code == 429: print(f"\n{colorize('[INFO] Rate limit hit. Waiting 60s...', Colors.YELLOW)}"); time.sleep(60); continue
                r.raise_for_status(); data = r.json()
                self.cache[cache_key] = data
                return data
            except requests.exceptions.RequestException as e: print(f"\n{colorize('[ERROR] API request failed: ' + str(e), Colors.RED)}"); return None

api_manager = APIManager()
found_lines = []
ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# --- Helper Functions ---
def colorize(text, color): return f"{color}{text}{Colors.END}"
def strip_colors(text): return ANSI_ESCAPE_PATTERN.sub('', text)
def colorize_ev(ev): return colorize(f"{ev:+.1f}", Colors.GREEN if ev > 0.5 else Colors.RED if ev < -0.5 else Colors.END)
def get_fen_from_san_sequence(moves):
    board = chess.Board()
    try:
        for move in moves: board.push_san(move)
        return board.fen(), "W" if board.turn == chess.WHITE else "B"
    except Exception as e: print(f"{colorize('Error parsing move sequence: ' + str(e), Colors.RED)}"); return None, None
def generate_lichess_url(moves):
    board, game = chess.Board(), chess.pgn.Game()
    node = game
    for move in moves:
        try: node = node.add_variation(board.push_san(move))
        except ValueError: return "Invalid move sequence"
    pgn = str(game).replace(" *", "")
    return f"https://lichess.org/analysis/pgn/{quote(pgn)}"
def calculate_p_value(move_stats, other_stats):
    observed = [list(move_stats), list(other_stats)]
    if sum(observed[1]) <= 0: return 0.0
    try: _, p, _, _ = chi2_contingency(observed); return p
    except ValueError: return 1.0

# --- "Line" Mode Logic ---
def print_line_reachability_stats(moves, speeds, ratings, interesting_move_san=None):
    headers = ["Move", "Played by", "Games", "p-value", "EV (×100)", "Raw %", "Move %", "If White Wants %", "If Black Wants %"]
    rows, board, white_wants, black_wants = [], chess.Board(), 1.0, 1.0
    root_data = api_manager.query(board.fen(), speeds, ratings)
    if not root_data or "white" not in root_data: return 0,0,'W',[], ""
    root_total = sum(root_data.get(k,0) for k in ['white','draws','black'])
    if root_total == 0: return 0,0,'W',[], ""
    root_ev = (root_data.get('white',0) - root_data.get('black',0)) / root_total * 100 if root_total else 0
    rows.append(["(start)", "-", f"{root_total:,}", "-", colorize_ev(root_ev), "100.00", "100.00", "100.00", "100.00"])
    prev_data, line_name = root_data, (root_data.get("opening") or {}).get("name")
    for move_san in moves:
        played_by = "W" if board.turn == chess.WHITE else "B"
        move_data = next((m for m in prev_data.get("moves",[]) if m.get("san") == move_san), None)
        if not move_data: break
        w,d,b = move_data.get("white",0), move_data.get("draws",0), move_data.get("black",0)
        parent_w, parent_d, parent_b = prev_data.get("white",0), prev_data.get("draws",0), prev_data.get("black",0)
        other_stats = (parent_w-w, parent_d-d, parent_b-b)
        p_value = calculate_p_value((w,d,b), other_stats)
        if p_value < 0.001: p_str = colorize("<0.001", Colors.GREEN)
        else: p_str = colorize(f"{p_value:.3f}", Colors.GREEN) if p_value < DEFAULT_HUNTER_CONFIG.P_VALUE_THRESHOLD else f"{p_value:.3f}"
        prev_total, move_total = parent_w + parent_d + parent_b, w+d+b
        move_pct = move_total / prev_total if prev_total > 0 else 0
        if played_by == "W": black_wants *= move_pct
        else: white_wants *= move_pct
        board.push_san(move_san)
        current_data = api_manager.query(board.fen(), speeds, ratings)
        if not current_data: break
        total = sum(current_data.get(k,0) for k in ['white','draws','black'])
        if total == 0: break
        ev = (current_data.get('white',0) - current_data.get('black',0)) / total * 100 if total else 0
        move_str = move_san + (colorize(" <-- Interesting", Colors.BLUE) if move_san == interesting_move_san else "")
        rows.append([move_str, played_by, f"{total:,}", p_str, colorize_ev(ev), f"{(total/root_total*100):.2f}", f"{move_pct*100:.2f}", f"{white_wants*100:.2f}", f"{black_wants*100:.2f}"])
        prev_data = current_data
        line_name = (current_data.get("opening") or {}).get("name")
    print(tabulate(rows, headers=headers, tablefmt="pretty"))
    return white_wants*100, black_wants*100, "W" if board.turn == chess.WHITE else "B", moves, line_name

def print_move_stats(fen, data, white_reach, black_reach, turn, move_list, p_val_thresh):
    player_str = "White" if turn == 'W' else "Black"
    print(f"\nFinal Position (FEN): {fen}\nLichess URL: {generate_lichess_url(move_list)}")
    print(f"If White wants, this position will be reached {white_reach:.2f}% of the time.")
    print(f"If Black wants, this position will be reached {black_reach:.2f}% of the time.\n")
    pos_w, pos_d, pos_b = data.get("white",0), data.get("draws",0), data.get("black",0)
    pos_total = pos_w + pos_d + pos_b
    pos_ev = ((pos_w - pos_b) / pos_total) if pos_total else 0
    best_move_san = None
    if pos_total > 0:
        moves_with_stats = []
        for m in data.get("moves", []):
            total = sum(m.get(k,0) for k in ['white','draws','black'])
            if total > 0: moves_with_stats.append({'san': m['san'], 'ev': (m['white'] - m['black']) / total})
        if moves_with_stats: best_move_san = (max if turn == 'W' else min)(moves_with_stats, key=lambda x: x['ev'])['san']
    headers, rows = ["Move", "Games", "EV", "ΔEV", "p-value", "Opening"], []
    parent_stats = (pos_w, pos_d, pos_b)
    for move in data.get("moves", []):
        w,d,b = move.get("white",0), move.get("draws",0), move.get("black",0)
        total = w+d+b; other_stats = (pos_w-w, pos_d-d, pos_b-b)
        if total == 0: continue
        move_ev = (w-b)/total if total > 0 else 0
        delta_ev = (move_ev - pos_ev) * 100
        p_value = calculate_p_value((w,d,b), other_stats)
        if p_value < 0.001: p_str = colorize("<0.001", Colors.GREEN)
        else: p_str = colorize(f"{p_value:.3f}", Colors.GREEN) if p_value < p_val_thresh else f"{p_value:.3f}"
        delta_ev_str = f"{delta_ev:+.1f}"
        if (turn == 'W' and delta_ev > 0.5) or (turn == 'B' and delta_ev < -0.5): delta_ev_str = colorize(delta_ev_str, Colors.GREEN)
        elif (turn == 'W' and delta_ev < -0.5) or (turn == 'B' and delta_ev > 0.5): delta_ev_str = colorize(delta_ev_str, Colors.RED)
        move_san_str = move.get("san","?") + (colorize(" <-- Best", Colors.BLUE) if move.get("san") == best_move_san else "")
        opening_name = (move.get("opening") or {}).get("name", "-")
        rows.append([move_san_str, f"{total:,}", colorize_ev(move_ev*100), delta_ev_str, p_str, opening_name])
    print(f"Next Move Statistics for {player_str}:"); print(tabulate(rows, headers=headers, tablefmt="pretty"))

def run_line_mode(args):
    print(colorize(f"\nAnalyzing line: {' '.join(args.moves) or '(start)'}", Colors.YELLOW))
    print(f"Speeds: {args.speeds} | Ratings: {args.ratings}")
    interesting_move = getattr(args, 'interesting_move_san', None)
    white_reach, black_reach, _, _, line_name = print_line_reachability_stats(args.moves, args.speeds, ratings=args.ratings, interesting_move_san=interesting_move)
    final_fen, final_turn = get_fen_from_san_sequence(args.moves)
    if not final_fen: return 1.0, 1.0, ""
    data = api_manager.query(final_fen, args.speeds, args.ratings)
    if data:
        print()
        print_move_stats(final_fen, data, white_reach, black_reach, final_turn, args.moves, DEFAULT_HUNTER_CONFIG.P_VALUE_THRESHOLD)
    return white_reach/100, black_reach/100, line_name

# --- "Hunt" Mode Logic ---
def find_interesting_lines_iterative(initial_board, initial_moves, start_white_prob, start_black_prob, speeds, ratings, config, max_finds):
    stack = [(initial_board.fen(), initial_moves, None, start_white_prob, start_black_prob, len(initial_moves))]
    visited_nodes, found_count = 0, 0
    parent_board = chess.Board()
    if initial_moves:
        for move in initial_moves[:-1]: parent_board.push_san(move)
        stack[0] = stack[0][:2] + (api_manager.query(parent_board.fen(), speeds, ratings),) + stack[0][3:]
    else:
        stack[0] = stack[0][:2] + (api_manager.query(initial_board.fen(), speeds, ratings),) + stack[0][3:]

    while stack:
        if max_finds and found_count >= max_finds:
            print(colorize(f"\nReached max finds limit ({max_finds}). Halting.", Colors.YELLOW))
            break
        fen, move_history, prev_pos_data, white_prob, black_prob, depth = stack.pop()
        board = chess.Board(fen)
        visited_nodes += 1
        indent = "  " * (depth - len(initial_moves))
        print(f"\r{indent}{colorize(f'[{visited_nodes: >3}|{len(stack): >3}]', Colors.GRAY)} Searching: {' '.join(move_history) or '(start)'}...", " " * 20, end="")
        current_data = api_manager.query(fen, speeds, ratings)
        if not current_data: continue
        total_games = sum(current_data.get(k, 0) for k in ['white', 'draws', 'black'])
        is_white_turn = board.turn == chess.WHITE
        reach_prob = white_prob if is_white_turn else black_prob
        if total_games < config.MIN_GAMES or depth >= config.MAX_DEPTH or reach_prob * 100 < config.MIN_REACH_PCT:
            continue
        prev_total = sum(prev_pos_data.get(k, 0) for k in ['white','draws','black'])
        if prev_total == 0: continue
        pos_ev = (prev_pos_data.get('white',0) - prev_pos_data.get('black',0)) / prev_total if prev_total > 0 else 0
        parent_stats = (prev_pos_data.get('white',0), prev_pos_data.get('draws',0), prev_pos_data.get('black',0))
        sorted_moves = sorted(current_data.get("moves",[]), key=lambda m: sum(m.get(k,0) for k in ['white','draws','black']), reverse=True)
        for move_data in sorted_moves:
            w,d,b = move_data.get("white",0), move_data.get("draws",0), move_data.get("black",0)
            move_total = w+d+b
            if move_total < config.MIN_GAMES: continue
            other_stats = (parent_stats[0]-w, parent_stats[1]-d, parent_stats[2]-b)
            p_value = calculate_p_value((w,d,b), other_stats)
            if p_value >= config.P_VALUE_THRESHOLD: continue
            move_ev = (w-b)/move_total if move_total > 0 else 0
            delta_ev = (move_ev - pos_ev) * 100
            if abs(delta_ev) > config.DELTA_EV_THRESHOLD:
                if (is_white_turn and delta_ev > 0) or (not is_white_turn and delta_ev < 0):
                    found_count += 1
                    full_line_moves = move_history + [move_data['san']]
                    player_name = "WHITE" if is_white_turn else "BLACK"
                    elo_gain = reach_prob * abs(delta_ev) * config.ELO_PER_POINT
                    opening_name = (move_data.get("opening") or {}).get("name", "no name")
                    report = {"line_moves": full_line_moves, "line_ev": move_ev * 100, "delta_ev": delta_ev, "p_value": p_value, "elo_gain": elo_gain, "opening_name": opening_name, "player": player_name, "reach_pct": reach_prob * 100}
                    found_lines.append(report)
                    title = f" FOUND OPPORTUNITY FOR {player_name} #{found_count} | ΔEV: {delta_ev:+.1f} | ELO Gain/100: {elo_gain:+.2f} "
                    print()
                    print(colorize("\n" + title.center(85, "="), Colors.BLUE))
                    run_line_mode(argparse.Namespace(moves=full_line_moves, speeds=speeds, ratings=ratings, interesting_move_san=move_data['san']))
                    print(colorize("="*85, Colors.BLUE) + "\n")
        for move_to_explore in reversed(sorted_moves[:config.BRANCH_FACTOR]):
            new_board = board.copy()
            new_board.push_san(move_to_explore['san'])
            move_pct = sum(move_to_explore.get(k,0) for k in ['white','draws','black']) / total_games if total_games else 0
            new_white_prob, new_black_prob = (white_prob, black_prob * move_pct) if is_white_turn else (white_prob * move_pct, black_prob)
            stack.append((new_board.fen(), move_history + [move_to_explore['san']], current_data, new_white_prob, new_black_prob, depth + 1))

def run_hunt_mode(args):
    global found_lines, interrupted_args, hunt_start_time, interrupted_line_name
    found_lines, interrupted_args = [], args
    config = DEFAULT_HUNTER_CONFIG
    hunt_start_time = time.time()
    print("--- WickedLines Blunder Hunt ---")
    print(f"Config: Min Games={config.MIN_GAMES}, Min Reach%={config.MIN_REACH_PCT}, ΔEV>|{config.DELTA_EV_THRESHOLD}|, p<{config.P_VALUE_THRESHOLD}, Branch={config.BRANCH_FACTOR}, ELO Gain Factor={config.ELO_PER_POINT}")
    board, start_white_prob, start_black_prob, line_name = chess.Board(), 1.0, 1.0, ""
    if args.moves:
        start_white_prob, start_black_prob, line_name = run_line_mode(argparse.Namespace(moves=args.moves, speeds=args.speeds, ratings=args.ratings))
        for move in args.moves:
            try: board.push_san(move)
            except ValueError: return
    interrupted_line_name = line_name
    print(f"\n--- Starting Hunt from position: {' '.join(args.moves) or '(start)'} ---")
    find_interesting_lines_iterative(board, args.moves, start_white_prob, start_black_prob, args.speeds, args.ratings, config, args.max_finds)
    hunt_duration = time.time() - hunt_start_time
    print(colorize("\n--- Hunt Complete ---", Colors.BLUE))
    if found_lines:
        print_final_summary(args, config, hunt_duration, line_name)
    print(f"Total API calls made: {api_manager.call_count} (many results were served from cache)")

# --- "Plot" and "Batch Plot" Mode Logic ---
def get_stats_for_line(moves, speed, rating_bracket):
    board = chess.Board()
    white_wants, black_wants = 1.0, 1.0
    line_name = "N/A"
    root_data = api_manager.query(board.fen(), speed, rating_bracket)
    if not root_data: return 0, 0, 0, 0, "API Error", "White"
    root_total_games = sum(root_data.get(k, 0) for k in ['white', 'draws', 'black'])
    if root_total_games == 0: root_total_games = 1
    
    root_ev = (root_data.get('white', 0) - root_data.get('black', 0)) / root_total_games * 100 if root_total_games > 0 else 0

    prev_data = root_data
    for move_san in moves:
        played_by = "W" if board.turn == chess.WHITE else "B"
        move_data = next((m for m in prev_data.get("moves", []) if m.get("san") == move_san), None)
        if not move_data: break
        parent_total_ply = sum(prev_data.get(k, 0) for k in ['white', 'draws', 'black'])
        if parent_total_ply == 0: break
        move_total = sum(move_data.get(k, 0) for k in ['white', 'draws', 'black'])
        move_pct = move_total / parent_total_ply if parent_total_ply > 0 else 0
        if played_by == "W": black_wants *= move_pct
        else: white_wants *= move_pct
        board.push_san(move_san)
        prev_data = api_manager.query(board.fen(), speed, rating_bracket)
        if not prev_data: break
        line_name = (prev_data.get("opening") or {}).get("name", line_name)
    is_last_move_by_white = len(moves) % 2 != 0
    forcing_player = "White" if is_last_move_by_white else "Black"
    reachability = white_wants if forcing_player == "White" else black_wants
    final_data = prev_data
    if not final_data: return 0, 0, 0, root_ev, line_name, forcing_player
    final_pos_total_games = sum(final_data.get(k, 0) for k in ['white', 'draws', 'black'])
    popularity = final_pos_total_games / root_total_games if root_total_games > 0 else 0
    if final_pos_total_games == 0:
        return 0, reachability * 100, popularity * 100, root_ev, line_name, forcing_player
    ev = (final_data.get('white', 0) - final_data.get('black', 0)) / final_pos_total_games * 100 if final_pos_total_games > 0 else 0
    return ev, reachability * 100, popularity * 100, root_ev, line_name, forcing_player

def run_plot_mode(args):
    print(colorize(f"\nGenerating plot for line: {' '.join(args.moves)}", Colors.YELLOW))
    print(f"Fixed Time Control: {args.speed}")
    print("Querying Lichess database for Elo brackets. This may take a moment...")

    (elo_gain_values, baseline_elo_gain_values, reachability_values,
     popularity_values, theory_advantage_values) = [], [], [], [], []
    final_line_name = "Unknown Opening"
    forcing_player = "White"
    numeric_elo_ratings = [int(r.replace('2500', '2600')) for r in PLOT_ELO_BRACKETS]
    ELO_FACTOR = 6

    for i, rating in enumerate(PLOT_ELO_BRACKETS):
        # get_stats_for_line returns ev as a percentage score (e.g., 5.0 for +5%)
        ev, reach, pop, root_ev, line_name, player = get_stats_for_line(args.moves, args.speed, rating)
        
        player_advantage = ev if player == 'White' else ev * -1
        baseline_advantage = root_ev if player == 'White' else root_ev * -1
        
        # Elo gain over 100 games = (Win% - Loss%) * Elo_Factor
        elo_gain_values.append(player_advantage * ELO_FACTOR)
        baseline_elo_gain_values.append(baseline_advantage * ELO_FACTOR)
        
        theory_advantage_values.append((reach / pop) if pop > 0 else 0)
        reachability_values.append(reach)
        popularity_values.append(pop)

        if line_name != "Unknown Opening": final_line_name = line_name
        forcing_player = player
        print(f"  ({i+1}/{len(PLOT_ELO_BRACKETS)}) Processed {rating} Elo... Elo Gain/100: {elo_gain_values[-1]:+.2f}")

    print(colorize("\nData collection complete. Generating final plot...", Colors.GREEN))

    plt.style.use('seaborn-v0_8-darkgrid')
    fig = plt.figure(figsize=(20, 16)) # Significantly larger figure
    fig.set_facecolor('#2E2E2E')

    # Define the grid layout for charts and the text/logo area
    gs = fig.add_gridspec(3, 2, height_ratios=[3, 2, 2.2], width_ratios=(1,1), hspace=0.4, wspace=0.25)
    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])
    text_ax = fig.add_subplot(gs[2, 0])
    logo_ax = fig.add_subplot(gs[2, 1])

    color_elo = '#57A8D8'
    color_reach = '#F07C32'
    color_pop = '#C875C4'
    color_theory = '#4ECDC4'
    color_base = '#B0B0B0'
    light_text_color = '#D3D3D3'

    for ax in [ax1, ax2, ax3]:
        ax.set_facecolor('#2E2E2E')
        for spine in ax.spines.values(): spine.set_edgecolor('gray')
        ax.tick_params(axis='y', colors=light_text_color, labelsize=12)
        ax.tick_params(axis='x', colors=light_text_color, labelsize=12, rotation=30, pad=10)
        ax.grid(True, which='major', axis='both', linestyle=':', linewidth=0.7, alpha=0.5)

    # Plot 1: Performance
    ax1.set_title("Performance", color=light_text_color, fontsize=18, weight='bold')
    ax1.set_ylabel("Exp. Elo Gain / 100 Games", color=color_elo, fontsize=14, weight='bold')
    ax1.plot(numeric_elo_ratings, elo_gain_values, 'o-', color=color_elo, label="Expected Elo Gain / 100 Games", markersize=8, linewidth=3)
    ax1.plot(numeric_elo_ratings, baseline_elo_gain_values, linestyle='-.', color=color_base, label=f"Average {forcing_player} Elo Gain / 100 Games", linewidth=2.5)
    ax1.axhline(0, color='lightgray', linestyle='--', linewidth=1.0, alpha=0.7)
    ax1.legend(facecolor='#424242', edgecolor='gray', labelcolor=light_text_color, fontsize=12)
    plt.setp(ax1.get_xticklabels(), rotation=0)

    # Plot 2: Reachability & Popularity
    ax2.set_title("Reachability & Popularity", color=light_text_color, fontsize=16, weight='bold')
    ax2.set_ylabel('Reachability %', color=color_reach, fontsize=12)
    ax2.plot(numeric_elo_ratings, reachability_values, 's--', color=color_reach, markersize=6, linewidth=2)
    ax2.set_ylim(bottom=0)
    ax2_twin = ax2.twinx()
    ax2_twin.set_ylabel('Popularity %', color=color_pop, fontsize=12)
    ax2_twin.plot(numeric_elo_ratings, popularity_values, 'd:', color=color_pop, markersize=6, linewidth=2)
    ax2_twin.spines['right'].set_edgecolor('gray')
    ax2_twin.tick_params(axis='y', colors=light_text_color, labelsize=12)
    ax2_twin.set_ylim(bottom=0)

    # Plot 3: Theory Advantage
    ax3.set_title("Theory Advantage", color=light_text_color, fontsize=16, weight='bold')
    ax3.set_ylabel('Advantage Ratio', color=color_theory, fontsize=12)
    ax3.plot(numeric_elo_ratings, theory_advantage_values, '*-', color=color_theory, markersize=8, linewidth=2)
    ax3.set_ylim(bottom=0)

    # Area 4: Text Explanations
    text_ax.axis('off')
    if forcing_player == 'White':
        elo_formula = f"(White Win % - Black Win %) * {ELO_FACTOR} * 100"
    else:
        elo_formula = f"(Black Win % - White Win %) * {ELO_FACTOR} * 100"

    # Two-column layout for text to prevent overlap
    bold_titles = [
        "Expected Elo Gain:",
        f"Average {forcing_player} Elo Gain:",
        "Reachability %:",
        "Popularity %:",
        "Theory Advantage:"
    ]
    descriptions = [
        f"{elo_formula}. Positive is good for {forcing_player}.",
        f"The average result for {forcing_player} from the game's starting position.",
        f"Chance to reach this position if {forcing_player} actively tries to play this line.",
        "Raw percentage of all games that follow this exact sequence of moves.",
        "Ratio of Reachability to Popularity. High values suggest a surprise weapon\nwhere preparation is highly efficient."
    ]
    
    y_pos = 1.0
    for i in range(len(bold_titles)):
        text_ax.text(0.0, y_pos, bold_titles[i], ha='left', va='top', fontsize=14, color=light_text_color, weight='bold', transform=text_ax.transAxes)
        text_ax.text(0.45, y_pos, descriptions[i], ha='left', va='top', fontsize=14, color=light_text_color, transform=text_ax.transAxes, linespacing=1.6)
        y_pos -= 0.22

    # Area 5: Logo
    logo_ax.axis('off')
    logo_filename = f"{''.join(args.moves)}_logo.png"
    if os.path.exists(logo_filename):
        try:
            img = plt.imread(logo_filename)
            logo_ax.imshow(img)
        except Exception as e:
            print(colorize(f"Warning: Could not load logo '{logo_filename}': {e}", Colors.YELLOW))

    # Global Title
    line_str = f"({' '.join(args.moves)})"
    title_opening_name = final_line_name if final_line_name not in ["Unknown Opening", "N/A"] else ""
    fig.suptitle(f"{title_opening_name} {line_str}", color=light_text_color, fontsize=24, weight='bold', y=0.99)
    
    fig.tight_layout(rect=[0.03, 0.03, 0.97, 0.95])
    
    plots_dir = "plots"
    os.makedirs(plots_dir, exist_ok=True)
    filename = f"{'_'.join(args.moves).replace(' ', '_')}_{args.speed}.png"
    filepath = os.path.join(plots_dir, filename)
    plt.savefig(filepath, dpi=150, facecolor=fig.get_facecolor())
    plt.show()
    
def run_batch_plot_mode(args):
    total_openings = len(BATCH_OPENINGS)
    print(colorize(f"Starting batch plot generation for {total_openings} openings...", Colors.YELLOW))
    print(f"Plots will be saved to the '{os.path.join(os.getcwd(), 'plots')}' directory.")
    
    for i, opening in enumerate(BATCH_OPENINGS):
        print(colorize(f"\n({i+1}/{total_openings}) Generating plot for: {opening['name']} ({opening['moves']})", Colors.BLUE))
        plot_args = argparse.Namespace(moves=opening['moves'].split(), speed=args.speed)
        try:
            run_plot_mode(plot_args, show_plot=False)
            print(colorize(f"Successfully generated plot for {opening['name']}.", Colors.GREEN))
        except Exception as e:
            print(colorize(f"Failed to generate plot for {opening['name']}: {e}", Colors.RED))
        
        time.sleep(1)

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
        if not os.path.exists(results_dir): return
        reports_data = []
        for filename in os.listdir(results_dir):
            if filename.endswith('.md'):
                parts = filename.replace('.md', '').split('_')
                data = {'path': os.path.join(results_dir, filename)}
                line_parts, config_parts = [], []
                config_started = False
                for part in parts:
                    if 'ratings-' in part or 'speeds-' in part or 'MD-' in part: config_started = True
                    if config_started: config_parts.append(part)
                    else: line_parts.append(part)
                data['line_slug'] = ' '.join(line_parts)
                for part in config_parts:
                    if 'ratings-' in part: data['ratings'] = part.replace('ratings-', '').replace('-',',')
                    if 'speeds-' in part: data['speeds'] = part.replace('speeds-', '').replace('-',',')
                    if 'MD-' in part: data['config_str'] = part.replace('-','=').replace('_',', ')
                reports_data.append(data)
        grouped_reports = {}
        for report in reports_data:
            line = report.get('line_slug', 'Unknown')
            if line not in grouped_reports: grouped_reports[line] = []
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
                        f.write(f"- **Ratings**: `{report.get('ratings','N/A')}` | **Speeds**: `{report.get('speeds','N/A')}` | **Config**: `{report.get('config_str','N/A')}` -> **[View Report]({report['path']})**\n")
                    f.write("\n")
        print(colorize(f"Updated master index file: {index_path}", Colors.YELLOW))
    except Exception as e: print(colorize(f"Could not update hunt index: {e}", Colors.RED))

def print_final_summary(args, config, hunt_duration, line_name):
    if not found_lines: return
    print(colorize("\n" + " Hunt Summary ".center(85, "-"), Colors.BLUE))
    print("Top opportunities ranked by expected ELO gain over 100 games:\n")
    file_output = ["# WickedLines Hunt Report", f"### For initial line: `{' '.join(args.moves) or '(start)'}` ({line_name or 'no name'})"]
    file_output.append(f"\n- **Date:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    file_output.append(f"- **Ratings:** `{args.ratings}` | **Speeds:** `{args.speeds}`")
    file_output.append(f"- **Config:** Min Games=`{config.MIN_GAMES}`, Max Depth=`{config.MAX_DEPTH}`, Min Reach=`{config.MIN_REACH_PCT}%`, Branch Factor=`{config.BRANCH_FACTOR}`")
    file_output.append(f"- **Analysis Duration:** `{hunt_duration:.2f} seconds`")
    file_output.append(f"- **API Calls:** `{api_manager.call_count}`")
    file_output.append("\n---\n\nTop opportunities ranked by expected ELO gain over 100 games:\n")
    sorted_report = sorted(found_lines, key=lambda x: x['elo_gain'], reverse=True)
    for i, item in enumerate(sorted_report):
        rank = i + 1
        p_str = "<0.001" if item['p_value'] < 0.001 else f"{item['p_value']:.3f}"
        elo_gain_str = f"ELO Gain/100: {item['elo_gain']:>+5.2f}"
        player_title = item['player'].title()
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
        with open(filepath, "w", encoding="utf-8") as f: f.write("\n".join(file_output))
        print(colorize(f"Successfully saved hunt report to: {filepath}", Colors.YELLOW))
        update_hunt_index(results_dir)
    except Exception as e: print(colorize(f"Error saving report to file: {e}", Colors.RED))

def signal_handler(sig, frame):
    print(colorize("\n\nHunt interrupted by user.", Colors.YELLOW))
    if 'hunt_start_time' in globals() and 'interrupted_args' in globals() and found_lines:
        print_final_summary(interrupted_args, DEFAULT_HUNTER_CONFIG, time.time() - hunt_start_time, interrupted_line_name)
    print(f"\nTotal API calls made during this session: {api_manager.call_count}"); sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    global interrupted_args, hunt_start_time, interrupted_line_name, found_lines
    interrupted_args, hunt_start_time, interrupted_line_name = None, 0.0, ""
    found_lines = []
    
    parser = argparse.ArgumentParser(
        description="WickedLines: A tool for chess opening analysis using the Lichess database.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Available modes")

    parser_line = subparsers.add_parser('line', help="Analyze a single, specific line of moves.")
    parser_line.add_argument("moves", nargs="+", help="Move list in SAN (e.g., e4 e5 Nf3 Nc6)")
    parser_line.add_argument("--speeds", default="blitz,rapid,classical", help="Comma-separated speed filters. Default: blitz,rapid,classical")
    parser_line.add_argument("--ratings", default="1600,1800", help="Comma-separated rating filters. Default: 1600,1800")
    parser_line.set_defaults(func=run_line_mode)

    parser_hunt = subparsers.add_parser('hunt', help="Recursively search for interesting opportunities and blunders.")
    parser_hunt.add_argument("moves", nargs="*", help="Optional initial move sequence to start the hunt from.")
    parser_hunt.add_argument("--speeds", default="blitz,rapid,classical", help="Comma-separated speed filters. Default: blitz,rapid,classical")
    parser_hunt.add_argument("--ratings", default="1600,1800", help="Comma-separated rating filters. Default: 1600,1800")
    parser_hunt.add_argument("--max-finds", type=int, help="Stop the search after finding N interesting lines.")
    parser_hunt.set_defaults(func=run_hunt_mode)

    parser_plot = subparsers.add_parser('plot', help="Plot the performance of an opening across all ELO ratings.")
    parser_plot.add_argument("moves", nargs="+", help="Move list in SAN to plot (e.g., e4 c6).")
    parser_plot.add_argument("--speed", default="rapid", choices=['blitz', 'rapid', 'classical'], help="A single, fixed time control for the plot. Default: rapid.")
    parser_plot.set_defaults(func=run_plot_mode)

    parser_batchplot = subparsers.add_parser('batchplot', help="Generate plots for a predefined list of major openings.")
    parser_batchplot.add_argument("--speed", default="rapid", choices=['blitz', 'rapid', 'classical'], help="A single, fixed time control for all plots. Default: rapid.")
    parser_batchplot.set_defaults(func=run_batch_plot_mode)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()