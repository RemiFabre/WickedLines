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

# --- Configuration ---
HunterConfig = namedtuple('HunterConfig', ['MIN_GAMES', 'MIN_REACH_PCT', 'DELTA_EV_THRESHOLD', 'P_VALUE_THRESHOLD', 'MAX_DEPTH', 'BRANCH_FACTOR', 'ELO_PER_POINT'])
DEFAULT_HUNTER_CONFIG = HunterConfig(MIN_GAMES=10000, MIN_REACH_PCT=1.0, DELTA_EV_THRESHOLD=5.0, P_VALUE_THRESHOLD=0.05, MAX_DEPTH=5, BRANCH_FACTOR=4, ELO_PER_POINT=8)

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
        if total_games < config.MIN_GAMES or depth >= config.MAX_DEPTH: continue
        if white_prob * 100 < config.MIN_REACH_PCT and black_prob * 100 < config.MIN_REACH_PCT: continue
        prev_total = sum(prev_pos_data.get(k, 0) for k in ['white','draws','black'])
        if prev_total == 0: continue
        pos_ev = (prev_pos_data.get('white',0) - prev_pos_data.get('black',0)) / prev_total
        parent_stats = (prev_pos_data.get('white',0), prev_pos_data.get('draws',0), prev_pos_data.get('black',0))
        sorted_moves = sorted(current_data.get("moves",[]), key=lambda m: sum(m.get(k,0) for k in ['white','draws','black']), reverse=True)
        for move_data in sorted_moves:
            w,d,b = move_data.get("white",0), move_data.get("draws",0), move_data.get("black",0)
            move_total = w+d+b; other_stats = (parent_stats[0]-w, parent_stats[1]-d, parent_stats[2]-b)
            if move_total < config.MIN_GAMES: continue
            p_value = calculate_p_value((w,d,b), other_stats)
            if p_value >= config.P_VALUE_THRESHOLD: continue
            move_ev = (w-b)/move_total; delta_ev = (move_ev - pos_ev) * 100
            
            is_good_for_player = (is_white_turn and delta_ev > config.DELTA_EV_THRESHOLD) or \
                                 (not is_white_turn and delta_ev < -config.DELTA_EV_THRESHOLD)
            has_leverage = (is_white_turn and white_prob > black_prob) or \
                           (not is_white_turn and black_prob > white_prob)

            if is_good_for_player and has_leverage:
                found_count += 1
                full_line_moves = move_history + [move_data['san']]
                player_name = "WHITE" if is_white_turn else "BLACK"
                reach_prob = white_prob if is_white_turn else black_prob
                elo_gain = reach_prob * abs(delta_ev) * config.ELO_PER_POINT
                opening_name = (move_data.get("opening") or {}).get("name", "no name")
                report = {"line_moves": full_line_moves, "line_ev": move_ev * 100, "delta_ev": delta_ev, "p_value": p_value, "elo_gain": elo_gain, "opening_name": opening_name, "player": player_name, "white_reach_pct": white_prob*100, "black_reach_pct": black_prob*100}
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
def update_hunt_index(results_dir="hunt_results"):
    index_path = "HUNT_INDEX.md"
    try:
        if not os.path.exists(results_dir): return
        dir_structure = {}
        for root, dirs, files in os.walk(results_dir):
            for file in files:
                if file.endswith('.md'):
                    rel_path = os.path.join(root, file)
                    parts = rel_path.split(os.sep)
                    if len(parts) >= 3:
                        group_key = (parts[1], parts[2])
                        if group_key not in dir_structure: dir_structure[group_key] = []
                        line_name = file.replace("_", " ").replace(".md", "")
                        if line_name == "start pos": line_name = "From Starting Position"
                        dir_structure[group_key].append((line_name, rel_path))
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("# WickedLines Hunt Results Index\n\n"); f.write("A collection of all opening opportunities discovered by the `hunt` command, grouped by configuration.\n\n")
            if not dir_structure: f.write("*No reports found yet. Run a hunt to generate one!*")
            else:
                for (ratings, speeds), reports in sorted(dir_structure.items()):
                    f.write(f"## Config: Ratings `{ratings}` | Speeds `{speeds}`\n\n")
                    for line_name, report_path in sorted(reports):
                        display_name = line_name
                        f.write(f"- [{display_name}]({report_path})\n")
                    f.write("\n")
        print(colorize(f"Updated master index file: {index_path}", Colors.YELLOW))
    except Exception as e: print(colorize(f"Could not update hunt index: {e}", Colors.RED))

def print_final_summary(args, hunt_duration):
    if not found_lines: return
    terminal_output = [colorize("\n" + " Hunt Summary ".center(85, "-"), Colors.BLUE), "Top opportunities ranked by expected ELO gain over 100 games:\n"]
    file_output = ["# WickedLines Hunt Report", f"### For initial line: `{' '.join(args.moves) or '(start)'}`"]
    file_output.append(f"- **Date:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
    file_output.append(f"- **Ratings:** `{args.ratings}` | **Speeds:** `{args.speeds}`")
    file_output.append(f"- **Config:** Min Games=`{DEFAULT_HUNTER_CONFIG.MIN_GAMES}`, Max Depth=`{DEFAULT_HUNTER_CONFIG.MAX_DEPTH}`, etc.")
    file_output.append(f"- **Analysis Duration:** `{hunt_duration:.2f} seconds`")
    file_output.append(f"- **API Calls:** `{api_manager.call_count}`")
    file_output.append("\n---\n"); file_output.append("\nTop opportunities ranked by expected ELO gain over 100 games:\n")
    
    sorted_report = sorted(found_lines, key=lambda x: x['elo_gain'], reverse=True)
    for i, item in enumerate(sorted_report):
        rank = i + 1
        p_str = "<0.001" if item['p_value'] < 0.001 else f"{item['p_value']:.3f}"
        elo_gain_str = f"ELO Gain/100: {item['elo_gain']:>+5.2f}"
        player_title = item['player'].title()
        delta_ev_str = f"{colorize_ev(item['delta_ev'])} (good for {player_title})"
        delta_ev_str_plain = f"{item['delta_ev']:+.1f} (good for {player_title})"
        white_reach, black_reach = item['white_reach_pct'], item['black_reach_pct']
        adv_player_reach, opp_player_reach = (white_reach, black_reach) if item['player'] == 'WHITE' else (black_reach, white_reach)
        theory_ratio = (adv_player_reach / opp_player_reach) if opp_player_reach > 0 else float('inf')
        reach_line = f"   {colorize('Reach & Leverage:', Colors.YELLOW)} "
        if item['player'] == 'WHITE':
            reach_line += f"White can force {white_reach:.2f}% of games. "
            reach_line += f"Black will face this {black_reach:.2f}% of the time. | "
        else:
            reach_line += f"Black can force {black_reach:.2f}% of games. "
            reach_line += f"White will face this {white_reach:.2f}% of the time. | "
        reach_line += f"Theory Ratio: {colorize(f'{theory_ratio:.2f}x', Colors.GREEN)}"
        line_str_color = colorize(' '.join(item['line_moves']), Colors.BLUE)
        opening_str = f"({colorize(item['opening_name'], Colors.GRAY)})"
        
        terminal_output.append(f"{rank}. {colorize(elo_gain_str, Colors.GREEN)} | {line_str_color} {opening_str}")
        terminal_output.append(reach_line)
        terminal_output.append(f"   {colorize('Impact:', Colors.YELLOW)}           Line EV: {colorize_ev(item['line_ev']):<14} | ΔEV: {delta_ev_str}")
        terminal_output.append(f"   {colorize('URL:', Colors.GRAY)}              {generate_lichess_url(item['line_moves'])}")
        terminal_output.append("")
        
        file_output.append(f"## {rank}. ELO Gain/100: `{item['elo_gain']:+.2f}` | Line: `{' '.join(item['line_moves'])}`")
        file_output.append(f"- **Opening:** {item['opening_name']}")
        file_output.append(f"- **Reach & Leverage:** White Wants: `{white_reach:.2f}%` | Black Wants: `{black_reach:.2f}%` | Theory Ratio: `{theory_ratio:.2f}x`")
        file_output.append(f"- **Impact:** Line EV: `{item['line_ev']:+.1f}`, ΔEV: `{delta_ev_str_plain}`")
        file_output.append(f"- **Significance (p-value):** `{p_str}`")
        file_output.append(f"- **[Analyze on Lichess]({generate_lichess_url(item['line_moves'])})**")
        file_output.append("\n---\n")

    print("\n".join(terminal_output))
    
    ratings_str = args.ratings.replace(",", "-"); speeds_str = args.speeds.replace(",", "-")
    results_dir = os.path.join("hunt_results", ratings_str, speeds_str)
    filename = "_".join(args.moves) + ".md" if args.moves else "start_pos.md"
    filepath = os.path.join(results_dir, filename)
    try:
        os.makedirs(results_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f: f.write("\n".join(file_output))
        print(colorize(f"Successfully saved hunt report to: {filepath}", Colors.YELLOW))
        update_hunt_index()
    except Exception as e: print(colorize(f"Error saving report to file: {e}", Colors.RED))

def signal_handler(sig, frame):
    print(colorize("\n\nHunt interrupted by user.", Colors.YELLOW))
    # FIX: Calculate duration and pass all required args to the summary function
    interruption_duration = time.time() - hunt_start_time
    print_final_summary(interrupted_args, interruption_duration)
    print(f"\nTotal API calls made during this session: {api_manager.call_count}")
    sys.exit(0)

def run_line_mode(args):
    print(colorize(f"\nAnalyzing line: {' '.join(args.moves) or '(start)'}", Colors.YELLOW))
    print(f"Speeds: {args.speeds} | Ratings: {args.ratings}")
    interesting_move = getattr(args, 'interesting_move_san', None)
    white_reach, black_reach, _, _, line_name = print_line_reachability_stats(args.moves, args.speeds, ratings=args.ratings, interesting_move_san=interesting_move)
    final_fen, final_turn = get_fen_from_san_sequence(args.moves)
    if not final_fen: return 1.0, 1.0, ""
    data = api_manager.query(final_fen, args.speeds, args.ratings)
    if data: print(); print_move_stats(final_fen, data, white_reach, black_reach, final_turn, args.moves, DEFAULT_HUNTER_CONFIG.P_VALUE_THRESHOLD)
    return white_reach/100, black_reach/100, line_name

def run_hunt_mode(args):
    global found_lines, interrupted_args, hunt_start_time;
    found_lines, interrupted_args, hunt_start_time = [], args, time.time()
    config = DEFAULT_HUNTER_CONFIG
    print("--- WickedLines Blunder Hunt ---")
    print(f"Config: Min Games={config.MIN_GAMES}, Min Reach%={config.MIN_REACH_PCT}, ΔEV>|{config.DELTA_EV_THRESHOLD}|, p<{config.P_VALUE_THRESHOLD}, Branch={config.BRANCH_FACTOR}, ELO Gain Factor={config.ELO_PER_POINT}")
    board, start_white_prob, start_black_prob = chess.Board(), 1.0, 1.0
    if args.moves:
        start_white_prob, start_black_prob, _ = run_line_mode(argparse.Namespace(moves=args.moves, speeds=args.speeds, ratings=args.ratings))
        for move in args.moves:
            try: board.push_san(move)
            except ValueError: return
    print(f"\n--- Starting Hunt from position: {' '.join(args.moves) or '(start)'} ---")
    find_interesting_lines_iterative(board, args.moves, start_white_prob, start_black_prob, args.speeds, args.ratings, config, args.max_finds)
    hunt_duration = time.time() - hunt_start_time
    print(colorize("\n--- Hunt Complete ---", Colors.BLUE))
    print_final_summary(args, hunt_duration)
    print(f"Total API calls made: {api_manager.call_count} (many results were served from cache)")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    interrupted_args = None; hunt_start_time = 0.0
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