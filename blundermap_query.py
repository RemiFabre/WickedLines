import chess
import requests
from tabulate import tabulate
import argparse
import time

API_BASE = "https://explorer.lichess.ovh/lichess"

def get_fen_from_san_sequence(moves_san, starting_fen=chess.STARTING_FEN):
    board = chess.Board(starting_fen)
    try:
        for move in moves_san:
            board.push_san(move)
        return board.fen(), board.turn
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
    r = requests.get(API_BASE, params=params)
    time.sleep(0.1)
    if r.status_code != 200:
        print(f"Error: API returned {r.status_code}")
        return None
    return r.json()

def print_line_reachability_stats(move_list, speeds, ratings):
    print("\nLine Reachability Stats:\n")
    headers = ["Move", "Turn", "Games", "White %", "Draw %", "Black %", "EV (×100)",
               "Raw %", "Move %", "If White Wants %", "If Black Wants %"]
    rows = []

    board = chess.Board()
    root_data = query_lichess_opening_explorer(board.fen(), speeds, ratings)
    root_total = root_data.get("white", 0) + root_data.get("draws", 0) + root_data.get("black", 0)
    if root_total == 0:
        print("Root position has 0 games. Cannot continue.")
        return

    cumulative_white = 1.0
    cumulative_black = 1.0
    white_path = [1.0]
    black_path = [1.0]
    move_percents = []

    for i in range(len(move_list) + 1):
        current_moves = move_list[:i]
        fen, turn = get_fen_from_san_sequence(current_moves)
        if not fen:
            break
        current_data = query_lichess_opening_explorer(fen, speeds, ratings)
        if not current_data:
            break

        white = current_data.get("white", 0)
        draws = current_data.get("draws", 0)
        black = current_data.get("black", 0)
        total = white + draws + black
        ev = ((white - black) / total) if total else 0
        raw_pct = (total / root_total) * 100 if root_total else 0
        move_pct = ""

        if_white = ""
        if_black = ""

        if i > 0:
            prev_moves = move_list[:i - 1]
            prev_fen, _ = get_fen_from_san_sequence(prev_moves)
            prev_data = query_lichess_opening_explorer(prev_fen, speeds, ratings)
            prev_total = prev_data.get("white", 0) + prev_data.get("draws", 0) + prev_data.get("black", 0)

            move_name = move_list[i - 1]
            freq = None
            for m in prev_data.get("moves", []):
                if m.get("san") == move_name:
                    freq = (m.get("white", 0) + m.get("draws", 0) + m.get("black", 0)) / prev_total if prev_total else 0
                    break
            move_pct = f"{freq * 100:.2f}" if freq is not None else ""
            move_percents.append(freq or 0)

            if not board.turn and freq is not None:  # White just moved
                cumulative_white *= freq
                white_path.append(cumulative_white)
                black_path.append(black_path[-1])
            elif board.turn and freq is not None:  # Black just moved
                cumulative_black *= freq
                black_path.append(cumulative_black)
                white_path.append(white_path[-1])
        else:
            move_percents.append(1.0)
            white_path = [1.0]
            black_path = [1.0]

        if board.turn:
            if_white = f"{white_path[-1] * 100:.2f}"
        else:
            if_black = f"{black_path[-1] * 100:.2f}"

        rows.append([
            move_list[i - 1] if i > 0 else "(start)",
            "W" if turn else "B",
            total,
            f"{white / total * 100:.1f}" if total else "-",
            f"{draws / total * 100:.1f}" if total else "-",
            f"{black / total * 100:.1f}" if total else "-",
            f"{ev * 100:.1f}",
            f"{raw_pct:.2f}",
            move_pct,
            if_white,
            if_black
        ])

        if i < len(move_list):
            board.push_san(move_list[i])

    # For last row: fill in missing reachability via decimating factor
    if len(rows) >= 2:
        last = rows[-1]
        prev_reach_white = white_path[-2]
        prev_reach_black = black_path[-2]
        last_move_side = "W" if last[1] == "B" else "B"
        last_move_factor = move_percents[-1]

        if last[9] == "":
            last[9] = f"{(prev_reach_white * last_move_factor) * 100:.2f}" if last_move_side == "W" else ""
        if last[10] == "":
            last[10] = f"{(prev_reach_black * last_move_factor) * 100:.2f}" if last_move_side == "B" else ""

    print(tabulate(rows, headers=headers, tablefmt="pretty"))
    print()

    return white_path[-1] * 100, black_path[-1] * 100, "W" if board.turn else "B", move_list

def print_move_stats(fen, data, white_reach, black_reach, turn, move_list):
    print(f"\nFinal Position (FEN): {fen}")
    print(f"Move sequence: {' '.join(move_list)}")
    print(f"Turn to play: {'White' if turn == 'W' else 'Black'}")
    print(f"Reached if White wants: {white_reach:.2f}%")
    print(f"Reached if Black wants: {black_reach:.2f}%\n")

    print(f"Current Opening: {data.get('opening', {}).get('name', 'Unknown')} ({data.get('opening', {}).get('eco', '-')})\n")

    root_white = data.get("white", 0)
    root_draws = data.get("draws", 0)
    root_black = data.get("black", 0)
    root_total = root_white + root_draws + root_black
    root_ev = ((root_white - root_black) / root_total) if root_total else 0

    root_table = [[
        "Final Node",
        root_total,
        f"{root_white / root_total * 100:.1f}" if root_total else "-",
        f"{root_draws / root_total * 100:.1f}" if root_total else "-",
        f"{root_black / root_total * 100:.1f}" if root_total else "-",
        f"{root_ev * 100:.1f}"
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
        delta_ev = (move_ev - root_ev) * 100
        opening_name = move["opening"]["name"] if move.get("opening") else "-"

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
        print("No moves found for this position.")
        return

    print("Next Move Statistics:")
    print(tabulate(rows, headers=headers, tablefmt="pretty"))

def main():
    parser = argparse.ArgumentParser(description="Query Lichess Opening Explorer")
    parser.add_argument("moves", nargs="+", help="Move list in SAN (e.g. e4 e5 Nf3 Nc6 Bb5)")
    parser.add_argument("--no-line-tracking", action="store_true", help="Skip line reachability stats")
    parser.add_argument("--speeds", default="blitz,rapid", help="Speed filters (e.g. blitz,rapid)")
    parser.add_argument("--ratings", default="1600,2400", help="Rating range (e.g. 1600,2400)")
    args = parser.parse_args()

    if not args.no_line_tracking:
        white_reach, black_reach, turn, move_list = print_line_reachability_stats(args.moves, args.speeds, args.ratings)
    else:
        white_reach = black_reach = turn = "?"
        move_list = args.moves

    final_fen, _ = get_fen_from_san_sequence(args.moves)
    if not final_fen:
        return

    data = query_lichess_opening_explorer(final_fen, speeds=args.speeds, ratings=args.ratings)
    if data:
        print_move_stats(final_fen, data, white_reach, black_reach, turn, move_list)

if __name__ == "__main__":
    main()
