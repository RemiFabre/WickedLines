#!/usr/bin/env python3
import chess
import requests
import time
import argparse
from tabulate import tabulate
from collections import namedtuple

# --- Configuration ---

HunterConfig = namedtuple('HunterConfig', [
    'MIN_GAMES', 'MIN_REACHABILITY_PCT', 'DELTA_EV_THRESHOLD', 'MAX_DEPTH', 'BRANCH_FACTOR'
])

DEFAULT_HUNTER_CONFIG = HunterConfig(
    MIN_GAMES=1000,
    MIN_REACHABILITY_PCT=1.0,
    DELTA_EV_THRESHOLD=8.0,
    MAX_DEPTH=20,
    BRANCH_FACTOR=3
)

# --- Color and Formatting ---

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    END = '\033[0m'

def colorize_ev(ev_value):
    # Use a small tolerance to avoid coloring near-zero values
    if ev_value > 0.5: return f"{Colors.GREEN}{ev_value:+.1f}{Colors.END}"
    if ev_value < -0.5: return f"{Colors.RED}{ev_value:+.1f}{Colors.END}"
    return f"{ev_value:+.1f}"

# --- API Management ---

class APIManager:
    def __init__(self):
        self.base_url = "https://explorer.lichess.ovh/lichess"
        self.cache = {}
        self.call_count = 0

    def query(self, fen, speeds, ratings):
        if fen in self.cache:
            return self.cache[fen]

        params = {"fen": fen, "variant": "standard", "speeds": speeds, "ratings": ratings}
        
        while True:
            self.call_count += 1
            print(f"\r{Colors.YELLOW}[API Calls: {self.call_count}]{Colors.END}", end="")
            
            try:
                r = requests.get(self.base_url, params=params)
                if r.status_code == 429:
                    print(f"\n{Colors.YELLOW}[INFO] Rate limit hit. Waiting for 60 seconds...{Colors.END}")
                    time.sleep(60)
                    continue
                r.raise_for_status()
                data = r.json()
                self.cache[fen] = data
                return data
            except requests.exceptions.RequestException as e:
                print(f"\n{Colors.RED}[ERROR] API request failed: {e}{Colors.END}")
                return None

api_manager = APIManager()

# --- Core Logic for "Line" Mode ---

def get_fen_from_san_sequence(moves_san):
    board = chess.Board()
    try:
        for move in moves_san:
            board.push_san(move)
        return board.fen(), "W" if board.turn == chess.WHITE else "B"
    except Exception as e:
        print(f"{Colors.RED}Error parsing move sequence: {e}{Colors.END}")
        return None, None

def print_line_reachability_stats(move_list, speeds, ratings):
    print("\nLine Reachability Stats:\n")
    headers = ["Move", "Played by", "Games", "White %", "Draw %", "Black %", "EV (×100)", "Raw %", "Move %", "If White Wants %", "If Black Wants %"]
    rows = []
    board = chess.Board()
    root_data = api_manager.query(board.fen(), speeds, ratings)
    if not root_data or "white" not in root_data: return 0, 0, 'W', []
    root_total = sum(root_data.get(k, 0) for k in ['white', 'draws', 'black'])
    if root_total == 0: return 0, 0, 'W', []

    white_wants, black_wants = 1.0, 1.0
    root_ev = (root_data.get('white',0) - root_data.get('black',0)) / root_total * 100 if root_total else 0
    # FIX: Applied colorize_ev here
    rows.append(["(start)", "-", root_total, f"{(root_data['white']/root_total*100):.1f}", f"{(root_data['draws']/root_total*100):.1f}", f"{(root_data['black']/root_total*100):.1f}", colorize_ev(root_ev), "100.00", "100.00", "100.00", "100.00"])

    prev_data = root_data
    for move_san in move_list:
        played_by = "W" if board.turn == chess.WHITE else "B"
        move_data = next((m for m in prev_data.get("moves", []) if m.get("san") == move_san), None)
        if not move_data: break
        
        prev_total = sum(prev_data.get(k, 0) for k in ['white', 'draws', 'black'])
        move_total = sum(move_data.get(k, 0) for k in ['white', 'draws', 'black'])
        move_pct = move_total / prev_total if prev_total else 0

        if played_by == "W": black_wants *= move_pct
        else: white_wants *= move_pct

        board.push_san(move_san)
        current_data = api_manager.query(board.fen(), speeds, ratings)
        if not current_data: break
        
        total = sum(current_data.get(k, 0) for k in ['white', 'draws', 'black'])
        if total == 0: break
        ev = (current_data.get('white',0) - current_data.get('black',0)) / total * 100 if total else 0
        raw_pct = total / root_total * 100
        # FIX: Applied colorize_ev here
        rows.append([move_san, played_by, total, f"{(current_data['white']/total*100):.1f}", f"{(current_data['draws']/total*100):.1f}", f"{(current_data['black']/total*100):.1f}", colorize_ev(ev), f"{raw_pct:.2f}", f"{move_pct*100:.2f}", f"{white_wants*100:.2f}", f"{black_wants*100:.2f}"])
        prev_data = current_data

    print() 
    print(tabulate(rows, headers=headers, tablefmt="pretty"))
    return white_wants * 100, black_wants * 100, "W" if board.turn == chess.WHITE else "B", move_list

def print_move_stats(fen, data, white_reach, black_reach, turn, move_list):
    print(f"\nFinal Position (FEN): {fen}")
    print(f"Move sequence: {' '.join(move_list)}")
    print(f"Turn to play: {'White' if turn == 'W' else 'Black'}")
    print(f"If White wants, this position will be reached {white_reach:.2f}% of the time.")
    print(f"If Black wants, this position will be reached {black_reach:.2f}% of the time.\n")
    
    pos_white, pos_draws, pos_black = data.get("white",0), data.get("draws",0), data.get("black",0)
    pos_total = pos_white + pos_draws + pos_black
    pos_ev = ((pos_white - pos_black) / pos_total) if pos_total else 0

    best_move_san = None
    if pos_total > 0:
        moves_with_stats = []
        for m in data.get("moves", []):
            total = m.get("white",0) + m.get("draws",0) + m.get("black",0)
            if total > 0: moves_with_stats.append({'san': m['san'], 'ev': (m['white'] - m['black']) / total})
        if moves_with_stats:
            best_move_san = (max if turn == 'W' else min)(moves_with_stats, key=lambda x: x['ev'])['san']

    headers = ["Move", "Games", "White %", "Draw %", "Black %", "EV (×100)", "ΔEV", "Avg Rating", "Opening"]
    rows = []
    for move in data.get("moves", []):
        white, draws, black = move.get("white",0), move.get("draws",0), move.get("black",0)
        total = white + draws + black
        if total == 0: continue
        move_ev, delta_ev = (white - black) / total, ((white - black) / total - pos_ev) * 100
        delta_ev_str = f"{delta_ev:+.1f}"
        if (turn == 'W' and delta_ev > 0.5) or (turn == 'B' and delta_ev < -0.5): delta_ev_str = f"{Colors.GREEN}{delta_ev_str}{Colors.END}"
        elif (turn == 'W' and delta_ev < -0.5) or (turn == 'B' and delta_ev > 0.5): delta_ev_str = f"{Colors.RED}{delta_ev_str}{Colors.END}"
        move_san_str = move.get("san","?") + (f" {Colors.BLUE}<-- Best{Colors.END}" if move.get("san") == best_move_san else "")
        opening_name = (move.get("opening") or {}).get("name", "-")
        rows.append([move_san_str, total, f"{white/total*100:.1f}", f"{draws/total*100:.1f}", f"{black/total*100:.1f}", colorize_ev(move_ev*100), delta_ev_str, move.get("averageRating", "-"), opening_name])
    
    print("Next Move Statistics:")
    print(tabulate(rows, headers=headers, tablefmt="pretty"))

# --- Core Logic for "Hunt" Mode ---
found_lines = []

def find_interesting_lines(board, move_history, prev_pos_data, white_wants_pct, black_wants_pct, depth, speeds, ratings, config):
    current_fen = board.fen()
    current_data = api_manager.query(current_fen, speeds, ratings)
    if not current_data: return

    total_games = sum(current_data.get(k, 0) for k in ['white', 'draws', 'black'])
    if total_games < config.MIN_GAMES: return
    if depth >= config.MAX_DEPTH: return
    
    is_white_turn = board.turn == chess.WHITE
    current_player_reachability = white_wants_pct if is_white_turn else black_wants_pct
    if current_player_reachability < config.MIN_REACHABILITY_PCT: return

    prev_total = sum(prev_pos_data.get(k, 0) for k in ['white', 'draws', 'black'])
    if prev_total == 0: return
    pos_ev = (prev_pos_data['white'] - prev_pos_data['black']) / prev_total

    sorted_moves = sorted(current_data.get("moves", []), key=lambda m: sum(m.get(k,0) for k in ['white','draws','black']), reverse=True)

    for move_data in sorted_moves:
        move_total = sum(move_data.get(k, 0) for k in ['white', 'draws', 'black'])
        if move_total == 0: continue
        
        move_ev, delta_ev = (move_data['white'] - move_data['black']) / move_total, ((move_data['white'] - move_data['black']) / move_total - pos_ev) * 100

        is_interesting = (is_white_turn and delta_ev > config.DELTA_EV_THRESHOLD) or \
                         (not is_white_turn and delta_ev < -config.DELTA_EV_THRESHOLD)

        if is_interesting:
            line_str = " ".join(move_history + [move_data['san']])
            found_lines.append({"line": line_str, "move": move_data['san'], "delta_ev": delta_ev, "played_by": "W" if is_white_turn else "B", "white_wants": white_wants_pct, "black_wants": black_wants_pct, "total_games": total_games})

    for i, move_to_explore in enumerate(sorted_moves):
        if i >= config.BRANCH_FACTOR: break
        move_san, move_total = move_to_explore['san'], sum(move_to_explore.get(k, 0) for k in ['white', 'draws', 'black'])
        move_pct = move_total / total_games if total_games else 0
        new_white_wants, new_black_wants = (white_wants_pct, black_wants_pct * move_pct) if is_white_turn else (white_wants_pct * move_pct, black_wants_pct)
        board.push_san(move_san)
        find_interesting_lines(board, move_history + [move_san], current_data, new_white_wants, new_black_wants, depth + 1, speeds, ratings, config)
        board.pop()

# --- Main Execution ---

def run_line_mode(args):
    print(f"Analyzing line: {' '.join(args.moves)}")
    print(f"Speeds: {args.speeds} | Ratings: {args.ratings}")
    
    white_reach, black_reach, turn, move_list = print_line_reachability_stats(args.moves, args.speeds, args.ratings)
    
    final_fen, final_turn = get_fen_from_san_sequence(args.moves)
    if not final_fen: return
    
    data = api_manager.query(final_fen, args.speeds, args.ratings)
    if data:
        print() 
        print_move_stats(final_fen, data, white_reach, black_reach, final_turn, args.moves)

def run_hunt_mode(args):
    config = DEFAULT_HUNTER_CONFIG
    print("Starting Blunder Hunt...")
    print(f"Config: Min Games={config.MIN_GAMES}, Min Reach%={config.MIN_REACHABILITY_PCT}, ΔEV Threshold={config.DELTA_EV_THRESHOLD}, Branch Factor={config.BRANCH_FACTOR}")
    print(f"Initial Line: {' '.join(args.moves) or '(start)'}\n")

    board = chess.Board()
    for move in args.moves:
        try: board.push_san(move)
        except ValueError: print(f"{Colors.RED}Illegal move: {move}{Colors.END}"); return
    
    prev_data_fen = chess.STARTING_FEN
    if len(args.moves) > 0:
        temp_board = chess.Board()
        for move in args.moves[:-1]: temp_board.push_san(move)
        prev_data_fen = temp_board.fen()
    prev_data = api_manager.query(prev_data_fen, args.speeds, args.ratings)
        
    find_interesting_lines(board, args.moves, prev_data, 100.0, 100.0, len(args.moves), args.speeds, args.ratings, config)
    
    print("\n\n--- Hunt Report: Found {} Interesting Lines ---\n".format(len(found_lines)))
    if not found_lines: print("No lines matching the criteria were found."); return

    sorted_report = sorted(found_lines, key=lambda x: abs(x['delta_ev']), reverse=True)
    headers = ["Move", "ΔEV", "Played by", "Reach % (Player)", "Full Line"]
    rows = []
    for item in sorted_report:
        player_reach = item['white_wants'] if item['played_by'] == 'W' else item['black_wants']
        rows.append([item['move'], colorize_ev(item['delta_ev']), item['played_by'], f"{player_reach:.2f}%", item['line']])
    print(tabulate(rows, headers=headers, tablefmt="pretty"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WickedLines: Chess Opening Reachability & Value Explorer.")
    parser.add_argument("--speeds", default="blitz,rapid,classical", help="Comma-separated speed filters")
    parser.add_argument("--ratings", default="1600,1800,2000,2200,2500", help="Comma-separated rating filters")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Available modes")
    parser_line = subparsers.add_parser('line', help="Analyze a single, specific line of moves.")
    parser_line.add_argument("moves", nargs="+", help="Move list in SAN (e.g. e4 e5 Nf3)")
    parser_line.set_defaults(func=run_line_mode)
    parser_hunt = subparsers.add_parser('hunt', help="Recursively search for interesting moves and blunders.")
    parser_hunt.add_argument("moves", nargs="*", help="Optional initial move sequence to start the hunt from.")
    parser_hunt.set_defaults(func=run_hunt_mode)
    args = parser.parse_args()
    args.func(args)