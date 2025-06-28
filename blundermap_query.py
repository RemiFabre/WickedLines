import chess
import chess.pgn
import requests
from tabulate import tabulate
import argparse

API_BASE = "https://explorer.lichess.ovh/lichess"

def get_fen_from_san_sequence(moves_san, starting_fen=chess.STARTING_FEN):
    board = chess.Board(starting_fen)
    try:
        for move in moves_san:
            board.push_san(move)
        return board.fen()
    except Exception as e:
        print(f"Error parsing move sequence: {e}")
        return None

def query_lichess_opening_explorer(fen, speeds="blitz,rapid", ratings="1600,2400"):
    params = {
        "fen": fen,
        "variant": "standard",
        "speeds": speeds,
        "ratings": ratings,
    }
    r = requests.get(API_BASE, params=params)
    if r.status_code != 200:
        print(f"Error: API returned {r.status_code}")
        return None
    return r.json()

def print_stats(fen, data):
    print(f"\nPosition (FEN): {fen}\n")
    print(f"Current Opening: {data.get('opening', {}).get('name', 'Unknown')} ({data.get('opening', {}).get('eco', '-')})\n")

    # -- Current state EV --
    root_white = data.get("white", 0)
    root_draws = data.get("draws", 0)
    root_black = data.get("black", 0)
    root_total = root_white + root_draws + root_black
    root_ev = ((root_white - root_black) / root_total) if root_total else 0

    # Print current node EV
    print("Current Position Statistics:")
    root_table = [[
        "Root",
        root_total,
        f"{root_white / root_total * 100:.1f}" if root_total else "-",
        f"{root_draws / root_total * 100:.1f}" if root_total else "-",
        f"{root_black / root_total * 100:.1f}" if root_total else "-",
        f"{root_ev * 100:.1f}"
    ]]
    print(tabulate(
        root_table,
        headers=["Node", "Games", "White %", "Draw %", "Black %", "EV (×100)"],
        tablefmt="pretty"
    ))
    print()

    # -- Next move stats --
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
    parser.add_argument("--speeds", default="blitz,rapid", help="Speed filters (e.g. blitz,rapid)")
    parser.add_argument("--ratings", default="1600,2400", help="Rating range (e.g. 1600,2400)")
    args = parser.parse_args()

    fen = get_fen_from_san_sequence(args.moves)
    if not fen:
        return

    data = query_lichess_opening_explorer(fen, speeds=args.speeds, ratings=args.ratings)
    if data:
        print_stats(fen, data)

if __name__ == "__main__":
    main()
