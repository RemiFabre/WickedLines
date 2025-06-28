import chess
import requests
from tabulate import tabulate
import argparse
import time

API_BASE = "https://explorer.lichess.ovh/lichess"

# This function is fine as is
def get_fen_from_san_sequence(moves_san, starting_fen=chess.STARTING_FEN):
    board = chess.Board(starting_fen)
    try:
        for move in moves_san:
            board.push_san(move)
        return board.fen(), "W" if board.turn == chess.WHITE else "B"
    except Exception as e:
        print(f"Error parsing move sequence: {e}")
        return None, None

def query_lichess_opening_explorer(fen, speeds="blitz,rapid", ratings="1600,2400"):
    params = {
        "fen": fen,
        "variant": "standard",
        "speeds": speeds,
        "ratings": ratings,
    }
    time.sleep(0.2)
    try:
        r = requests.get(API_BASE, params=params)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error: {e}")
        return None

# --- FULLY CORRECTED FUNCTION BASED ON YOUR LOGIC ---
def print_line_reachability_stats(move_list, speeds, ratings):
    print("\nLine Reachability Stats:\n")
    # UPDATED: Changed "Turn" to "Played by" as requested
    headers = ["Move", "Played by", "Games", "White %", "Draw %", "Black %", "EV (×100)",
               "Raw %", "Move %", "If White Wants %", "If Black Wants %"]
    rows = []

    board = chess.Board()

    root_data = query_lichess_opening_explorer(board.fen(), speeds, ratings)
    if not root_data or ("white" not in root_data and "draws" not in root_data and "black" not in root_data):
        print("Could not fetch data for the starting position. Aborting.")
        return 0, 0, 'W', []

    root_total_games = root_data.get("white", 0) + root_data.get("draws", 0) + root_data.get("black", 0)
    if root_total_games == 0:
        print("Root position has 0 games in the database. Cannot continue.")
        return 0, 0, 'W', []

    # Initialize variables for the loop
    cumulative_if_white_wants = 1.0
    cumulative_if_black_wants = 1.0

    root_white_wins = root_data.get("white", 0)
    root_draws = root_data.get("draws", 0)
    root_black_wins = root_data.get("black", 0)
    root_ev = ((root_white_wins - root_black_wins) / root_total_games) if root_total_games else 0

    # Add the starting position row
    rows.append([
        "(start)",
        "-",  # UPDATED: No one "played" to get to the start
        root_total_games,
        f"{(root_white_wins / root_total_games * 100):.1f}",
        f"{(root_draws / root_total_games * 100):.1f}",
        f"{(root_black_wins / root_total_games * 100):.1f}",
        f"{root_ev * 100:.1f}",
        "100.00",
        "100.00",
        f"{cumulative_if_white_wants * 100:.2f}",
        f"{cumulative_if_black_wants * 100:.2f}"
    ])

    prev_pos_data = root_data
    for move_san in move_list:
        # Determine who is making the current move BEFORE pushing it to the board
        played_by = "W" if board.turn == chess.WHITE else "B"

        move_data = next((m for m in prev_pos_data.get("moves", []) if m.get("san") == move_san), None)
        if not move_data:
            print(f"\nWarning: Move '{move_san}' not found in the database. Halting analysis.")
            break

        prev_pos_total_games = prev_pos_data.get("white", 0) + prev_pos_data.get("draws", 0) + prev_pos_data.get("black", 0)
        move_total_games = move_data.get("white", 0) + move_data.get("draws", 0) + move_data.get("black", 0)
        move_pct = move_total_games / prev_pos_total_games if prev_pos_total_games else 0

        # --- CORRECTED LOGIC ---
        # If White plays, Black's path probability is decimated.
        # If Black plays, White's path probability is decimated.
        if played_by == "W":
            cumulative_if_black_wants *= move_pct
        else:  # played_by == "B"
            cumulative_if_white_wants *= move_pct
        # --- END OF CORRECTION ---

        try:
            board.push_san(move_san)
        except ValueError as e:
            print(f"Illegal move '{move_san}'. Halting analysis. Error: {e}")
            break

        current_pos_data = query_lichess_opening_explorer(board.fen(), speeds, ratings)
        if not current_pos_data:
            print(f"Could not fetch data for position after '{move_san}'. Halting analysis.")
            break

        white_wins = current_pos_data.get("white", 0)
        draws = current_pos_data.get("draws", 0)
        black_wins = current_pos_data.get("black", 0)
        total_games = white_wins + draws + black_wins
        if total_games == 0:
             print(f"\nWarning: Position after '{move_san}' has 0 games. Halting analysis.")
             break

        ev = ((white_wins - black_wins) / total_games) * 100
        raw_pct = (total_games / root_total_games) * 100
        turn_after_move = "B" if board.turn == chess.BLACK else "W"

        rows.append([
            move_san,
            played_by, # UPDATED: Show who made the move
            total_games,
            f"{(white_wins / total_games * 100):.1f}",
            f"{(draws / total_games * 100):.1f}",
            f"{(black_wins / total_games * 100):.1f}",
            f"{ev:.1f}",
            f"{raw_pct:.2f}",
            f"{move_pct * 100:.2f}",
            f"{cumulative_if_white_wants * 100:.2f}",
            f"{cumulative_if_black_wants * 100:.2f}"
        ])

        prev_pos_data = current_pos_data

    print(tabulate(rows, headers=headers, tablefmt="pretty"))
    print()

    final_turn = "W" if board.turn == chess.WHITE else "B"
    return cumulative_if_white_wants * 100, cumulative_if_black_wants * 100, final_turn, move_list


# (The rest of the script: print_move_stats, main, etc. is unchanged and correct)
def print_move_stats(fen, data, white_reach, black_reach, turn, move_list):
    print(f"\nFinal Position (FEN): {fen}")
    print(f"Move sequence: {' '.join(move_list)}")
    print(f"Turn to play: {'White' if turn == 'W' else 'Black'}")
    print(f"Reached if White wants: {white_reach:.2f}%")
    print(f"Reached if Black wants: {black_reach:.2f}%\n")

    opening_info = data.get('opening')
    if opening_info:
        print(f"Current Opening: {opening_info.get('name', 'Unknown')} ({opening_info.get('eco', '-')})\n")

    pos_white = data.get("white", 0)
    pos_draws = data.get("draws", 0)
    pos_black = data.get("black", 0)
    pos_total = pos_white + pos_draws + pos_black
    pos_ev = ((pos_white - pos_black) / pos_total) if pos_total else 0

    root_table = [[
        "Final Node",
        pos_total,
        f"{pos_white / pos_total * 100:.1f}" if pos_total else "-",
        f"{pos_draws / pos_total * 100:.1f}" if pos_total else "-",
        f"{pos_black / pos_total * 100:.1f}" if pos_total else "-",
        f"{pos_ev * 100:.1f}"
    ]]
    print("Final Position Statistics:")
    print(tabulate(root_table, headers=["Node", "Games", "White %", "Draw %", "Black %", "EV (×100)"], tablefmt="pretty"))
    print()

    headers = ["Move", "Games", "White %", "Draw %", "Black %", "EV (×100)", "ΔEV", "Avg Rating", "Opening"]
    rows = []

    for move in data.get("moves", []):
        white = move.get("white", 0)
        draws = move.get("draws", 0)
        black = move.get("black", 0)
        total = white + draws + black
        if total == 0:
            continue

        move_ev = (white - black) / total
        delta_ev = (move_ev - pos_ev) * 100
        opening_name = move.get("opening", {}).get("name") if move.get("opening") else "-"

        rows.append([
            move.get("san", "?"),
            total,
            f"{white / total * 100:.1f}",
            f"{draws / total * 100:.1f}",
            f"{black / total * 100:.1f}",
            f"{move_ev * 100:.1f}",
            f"{delta_ev:+.1f}",
            move.get("averageRating", "-"),
            opening_name
        ])

    if not rows:
        print("No further moves found in the database for this position.")
        return

    print("Next Move Statistics:")
    print(tabulate(rows, headers=headers, tablefmt="pretty"))


def main():
    parser = argparse.ArgumentParser(
        description="WickedLines: Chess Opening Reachability & Value Explorer.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("moves", nargs="*", help="Move list in SAN (e.g. e4 e5 Nf3 Nc6). If empty, shows stats for the starting position.")
    parser.add_argument("--no-line-tracking", action="store_true", help="Skip the detailed line reachability table.")
    parser.add_argument("--speeds", default="blitz,rapid,classical", help="Comma-separated speed filters (e.g. blitz,rapid)")
    parser.add_argument("--ratings", default="1600,1800,2000,2200,2500", help="Comma-separated rating filters (e.g. 2000,2200)")
    args = parser.parse_args()

    white_reach, black_reach, turn = 100.0, 100.0, 'W'
    if args.moves and not args.no_line_tracking:
        white_reach, black_reach, turn, _ = print_line_reachability_stats(args.moves, args.speeds, args.ratings)

    final_fen, final_turn = get_fen_from_san_sequence(args.moves)
    if final_fen is None:
        return

    data = query_lichess_opening_explorer(final_fen, speeds=args.speeds, ratings=args.ratings)
    if data:
        print_move_stats(final_fen, data, white_reach, black_reach, final_turn, args.moves)


if __name__ == "__main__":
    main()