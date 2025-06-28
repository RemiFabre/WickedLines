#!/usr/bin/env python3
import chess
import chess.pgn
import requests
import time
import argparse
import signal
import sys
from urllib.parse import quote
from tabulate import tabulate
from collections import namedtuple
from scipy.stats import chi2_contingency

# --- Configuration ---
HunterConfig = namedtuple('HunterConfig', ['MIN_GAMES', 'MIN_REACH_PCT', 'DELTA_EV_THRESHOLD', 'P_VALUE_THRESHOLD', 'MAX_DEPTH', 'BRANCH_FACTOR', 'ELO_PER_POINT'])
DEFAULT_HUNTER_CONFIG = HunterConfig(MIN_GAMES=200, MIN_REACH_PCT=0.5, DELTA_EV_THRESHOLD=5.0, P_VALUE_THRESHOLD=0.05, MAX_DEPTH=25, BRANCH_FACTOR=3, ELO_PER_POINT=8)

# --- Global State & Classes ---
class Colors:
    GREEN, RED, BLUE, YELLOW, GRAY, END = '\033[92m', '\033[91m', '\033[94m', '\033[93m', '\033[90m', '\033[0m'

class APIManager:
    def __init__(self):
        self.base_url = "https://explorer.lichess.ovh/lichess"
        self.cache = {}
        self.call_count = 0
    def query(self, fen, speeds, ratings):
        if fen in self.cache: return self.cache[fen]
        params = {"fen": fen, "variant": "standard", "speeds": speeds, "ratings": ratings}
        while True:
            self.call_count += 1
            try:
                r = requests.get(self.base_url, params=params)
                if r.status_code == 429: print(f"\n{colorize('[INFO] Rate limit hit. Waiting 60s...', Colors.YELLOW)}"); time.sleep(60); continue
                r.raise_for_status(); data = r.json(); self.cache[fen] = data; return data
            except requests.exceptions.RequestException as e: print(f"\n{colorize('[ERROR] API request failed: ' + str(e), Colors.RED)}"); return None

api_manager = APIManager()
found_lines = []

# --- Helper Functions ---
def colorize(text, color): return f"{color}{text}{Colors.END}"
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
    headers = ["Move", "Played by", "Games", "White %", "Draw %", "Black %", "EV (×100)", "Raw %", "Move %", "If White Wants %", "If Black Wants %"]
    rows, board, white_wants, black_wants = [], chess.Board(), 1.0, 1.0
    root_data = api_manager.query(board.fen(), speeds, ratings)
    if not root_data or "white" not in root_data: return 0,0,'W',[]
    root_total = sum(root_data.get(k,0) for k in ['white','draws','black'])
    if root_total == 0: return 0,0,'W',[]
    root_ev = (root_data.get('white',0) - root_data.get('black',0)) / root_total * 100 if root_total else 0
    rows.append(["(start)", "-", f"{root_total:,}", f"{(root_data['white']/root_total*100):.1f}", f"{(root_data['draws']/root_total*100):.1f}", f"{(root_data['black']/root_total*100):.1f}", colorize_ev(root_ev), "100.00", "100.00", "100.00", "100.00"])
    prev_data = root_data
    for move_san in moves:
        played_by = "W" if board.turn == chess.WHITE else "B"
        move_data = next((m for m in prev_data.get("moves",[]) if m.get("san") == move_san), None)
        if not move_data: break
        prev_total = sum(prev_data.get(k,0) for k in ['white','draws','black'])
        move_total = sum(move_data.get(k,0) for k in ['white','draws','black'])
        move_pct = move_total / prev_total if prev_total else 0
        if played_by == "W": black_wants *= move_pct
        else: white_wants *= move_pct
        board.push_san(move_san)
        current_data = api_manager.query(board.fen(), speeds, ratings)
        if not current_data: break
        total = sum(current_data.get(k,0) for k in ['white','draws','black'])
        if total == 0: break
        ev = (current_data.get('white',0) - current_data.get('black',0)) / total * 100 if total else 0
        move_str = move_san + (colorize(" <-- Interesting", Colors.BLUE) if move_san == interesting_move_san else "")
        rows.append([move_str, played_by, f"{total:,}", f"{(current_data['white']/total*100):.1f}", f"{(current_data['draws']/total*100):.1f}", f"{(current_data['black']/total*100):.1f}", colorize_ev(ev), f"{(total/root_total*100):.2f}", f"{move_pct*100:.2f}", f"{white_wants*100:.2f}", f"{black_wants*100:.2f}"])
        prev_data = current_data
    print(tabulate(rows, headers=headers, tablefmt="pretty"))
    return white_wants*100, black_wants*100, "W" if board.turn == chess.WHITE else "B", moves

def print_move_stats(fen, data, white_reach, black_reach, turn, move_list, p_val_thresh):
    player_str = "White" if turn == 'W' else "Black"
    print(f"\nFinal Position (FEN): {fen}")
    print(f"Lichess URL: {generate_lichess_url(move_list)}")
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
    headers = ["Move", "Games", "EV", "ΔEV", "p-value", "Opening"]
    rows = []
    parent_stats = (pos_w, pos_d, pos_b)
    for move in data.get("moves", []):
        w,d,b = move.get("white",0), move.get("draws",0), move.get("black",0)
        total = w+d+b; other_stats = (pos_w-w, pos_d-d, pos_b-b)
        if total == 0: continue
        move_ev = (w-b)/total; delta_ev = (move_ev - pos_ev) * 100
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

# --- "Hunt" Mode Logic ---
def find_interesting_lines_iterative(initial_board, initial_moves, start_white_prob, start_black_prob, speeds, ratings, config, max_finds):
    stack = [(initial_board.fen(), initial_moves, None, start_white_prob, start_black_prob, len(initial_moves))]
    visited_nodes, found_count = 0, 0
    parent_board = chess.Board()
    for move in initial_moves[:-1]: parent_board.push_san(move)
    stack[0] = stack[0][:2] + (api_manager.query(parent_board.fen(), speeds, ratings),) + stack[0][3:]

    while stack:
        if max_finds and found_count >= max_finds: print(colorize(f"\nReached max finds limit ({max_finds}). Halting.", Colors.YELLOW)); break
        fen, move_history, prev_pos_data, white_prob, black_prob, depth = stack.pop()
        board = chess.Board(fen); visited_nodes += 1
        indent = "  " * (depth - len(initial_moves))
        print(f"\r{indent}{colorize(f'[{visited_nodes: >3}|{len(stack): >3}]', Colors.GRAY)} Searching: {' '.join(move_history) or '(start)'}...", " " * 20, end="")
        current_data = api_manager.query(fen, speeds, ratings)
        if not current_data: continue
        total_games = sum(current_data.get(k, 0) for k in ['white', 'draws', 'black'])
        is_white_turn = board.turn == chess.WHITE
        reach_prob = white_prob if is_white_turn else black_prob
        if total_games < config.MIN_GAMES or depth >= config.MAX_DEPTH or reach_prob * 100 < config.MIN_REACH_PCT: continue
        prev_total = sum(prev_pos_data.get(k, 0) for k in ['white','draws','black'])
        if prev_total == 0: continue
        pos_ev = (prev_pos_data.get('white',0) - prev_pos_data.get('black',0)) / prev_total
        parent_stats = (prev_pos_data.get('white',0), prev_pos_data.get('draws',0), prev_pos_data.get('black',0))
        sorted_moves = sorted(current_data.get("moves",[]), key=lambda m: sum(m.get(k,0) for k in ['white','draws','black']), reverse=True)
        for move_data in sorted_moves:
            w,d,b = move_data.get("white",0), move_data.get("draws",0), move_data.get("black",0)
            move_total = w+d+b; other_stats = (parent_stats[0]-w, parent_stats[1]-d, parent_stats[2]-b)
            if move_total == 0: continue
            p_value = calculate_p_value((w,d,b), other_stats)
            if p_value >= config.P_VALUE_THRESHOLD: continue
            move_ev = (w-b)/move_total; delta_ev = (move_ev - pos_ev) * 100
            if abs(delta_ev) > config.DELTA_EV_THRESHOLD:
                if (is_white_turn and delta_ev > 0) or (not is_white_turn and delta_ev < 0):
                    found_count += 1
                    full_line_moves = move_history + [move_data['san']]
                    player_name = "WHITE" if is_white_turn else "BLACK"
                    elo_gain = reach_prob * abs(delta_ev) * config.ELO_PER_POINT
                    opening_name = (move_data.get("opening") or {}).get("name", "no name")
                    report = {"line_moves": full_line_moves, "move": move_data['san'], "delta_ev": delta_ev, "p_value": p_value, "elo_gain": elo_gain, "opening_name": opening_name, "player": player_name, "reach_pct": reach_prob * 100}
                    found_lines.append(report)
                    title = f" FOUND OPPORTUNITY FOR {player_name} #{found_count} | ΔEV: {delta_ev:+.1f} | ELO Gain/100: {elo_gain:+.2f} "
                    print(); print(colorize("\n" + title.center(85, "="), Colors.BLUE))
                    run_line_mode(argparse.Namespace(moves=full_line_moves, speeds=speeds, ratings=ratings, interesting_move_san=move_data['san']))
                    print(colorize("="*85, Colors.BLUE) + "\n")

        for i, move_to_explore in enumerate(reversed(sorted_moves[:config.BRANCH_FACTOR])):
            new_board, move_san = board.copy(), move_to_explore['san']
            new_board.push_san(move_san)
            move_pct = sum(move_to_explore.get(k,0) for k in ['white','draws','black']) / total_games if total_games else 0
            new_white_prob, new_black_prob = (white_prob, black_prob * move_pct) if is_white_turn else (white_prob * move_pct, black_prob)
            stack.append((new_board.fen(), move_history + [move_san], current_data, new_white_prob, new_black_prob, depth + 1))

# --- Main Execution & Signal Handling ---
def print_final_summary():
    if not found_lines: return
    print(colorize("\n" + " Hunt Summary ".center(85, "-"), Colors.BLUE))
    print("Top opportunities ranked by expected ELO gain over 100 games:\n")
    sorted_report = sorted(found_lines, key=lambda x: x['elo_gain'], reverse=True)
    for i, item in enumerate(sorted_report):
        rank = i + 1
        p_str = colorize("<0.001", Colors.GREEN) if item['p_value'] < 0.001 else colorize(f"{item['p_value']:.3f}", Colors.GREEN)
        elo_gain_str = f"ELO Gain/100: {item['elo_gain']:>+5.2f}"
        delta_ev_val = item['delta_ev']
        player_title = item['player'].title()
        delta_ev_str = f"{colorize_ev(delta_ev_val)} (good for {player_title})"
        
        # FIX: Added the "Reachable" percentage to the final summary
        reach_pct_str = f"Reachable: {item['reach_pct']:.2f}%"

        print(f"{rank}. {colorize(elo_gain_str, Colors.GREEN)} | "
              f"{colorize(reach_pct_str, Colors.YELLOW)} | "
              f"Move: {colorize(item['move'], Colors.BLUE):<5} | "
              f"ΔEV: {delta_ev_str}")
              
        opening_str = f"({colorize(item['opening_name'], Colors.GRAY)})"
        print(f"   {colorize('Line:', Colors.GRAY)} {' '.join(item['line_moves'])} {opening_str}")
        print(f"   {colorize('URL:', Colors.GRAY)}  {generate_lichess_url(item['line_moves'])}")
        print() 

def signal_handler(sig, frame):
    print(colorize("\n\nHunt interrupted by user.", Colors.YELLOW))
    print_final_summary()
    print(f"\nTotal API calls made during this session: {api_manager.call_count}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def run_line_mode(args):
    print(colorize(f"\nAnalyzing line: {' '.join(args.moves) or '(start)'}", Colors.YELLOW))
    print(f"Speeds: {args.speeds} | Ratings: {args.ratings}")
    interesting_move = getattr(args, 'interesting_move_san', None)
    white_reach, black_reach, turn, move_list = print_line_reachability_stats(args.moves, args.speeds, ratings=args.ratings, interesting_move_san=interesting_move)
    final_fen, final_turn = get_fen_from_san_sequence(args.moves)
    if not final_fen: return 1.0, 1.0 
    data = api_manager.query(final_fen, args.speeds, args.ratings)
    if data: print(); print_move_stats(final_fen, data, white_reach, black_reach, final_turn, args.moves, DEFAULT_HUNTER_CONFIG.P_VALUE_THRESHOLD)
    return white_reach/100, black_reach/100 

def run_hunt_mode(args):
    global found_lines; found_lines = []
    config = DEFAULT_HUNTER_CONFIG
    print("--- WickedLines Blunder Hunt ---")
    print(f"Config: Min Games={config.MIN_GAMES}, Min Reach%={config.MIN_REACH_PCT}, ΔEV>|{config.DELTA_EV_THRESHOLD}|, p<{config.P_VALUE_THRESHOLD}, Branch={config.BRANCH_FACTOR}, ELO Gain Factor={config.ELO_PER_POINT}")
    board, start_white_prob, start_black_prob = chess.Board(), 1.0, 1.0
    if args.moves:
        start_white_prob, start_black_prob = run_line_mode(argparse.Namespace(moves=args.moves, speeds=args.speeds, ratings=args.ratings))
        for move in args.moves:
            try: board.push_san(move)
            except ValueError: return
    print(f"\n--- Starting Hunt from position: {' '.join(args.moves) or '(start)'} ---")
    find_interesting_lines_iterative(board, args.moves, start_white_prob, start_black_prob, args.speeds, args.ratings, config, args.max_finds)
    print(colorize("\n--- Hunt Complete ---", Colors.BLUE))
    print_final_summary()
    print(f"Total API calls made: {api_manager.call_count} (many results were served from cache)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WickedLines: Chess Opening Reachability & Value Explorer.")
    parser.add_argument("--speeds", default="blitz,rapid,classical", help="Comma-separated speed filters")
    parser.add_argument("--ratings", default="1400,1600,1800", help="Comma-separated rating filters")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Available modes")
    parser_line = subparsers.add_parser('line', help="Analyze a single, specific line of moves.")
    parser_line.add_argument("moves", nargs="+", help="Move list in SAN")
    parser_line.set_defaults(func=run_line_mode)
    parser_hunt = subparsers.add_parser('hunt', help="Recursively search for interesting moves and blunders.")
    parser_hunt.add_argument("moves", nargs="*", help="Optional initial move sequence to start the hunt from.")
    parser_hunt.add_argument("--max-finds", type=int, help="Stop after finding N interesting lines.")
    parser_hunt.set_defaults(func=run_hunt_mode)
    args = parser.parse_args()
    args.func(args)