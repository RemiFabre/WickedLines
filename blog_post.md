# Finding Opening Gold: A Statistical Hunt for Wicked Lines

Introducing a Python tool that uses the Lichess API to hunt for opening lines and traps that are both practical and likely to appear in your games. It's designed to find statistical trends, surprising refutations, and underrated repertoire choices.

The tool, "WickedLines," is open-source under the MIT license (meaning it's fully permissive). Anyone is free to play with it, but be warned: it's fresh out of the oven and has no Graphical User Interface other than the terminal. 

**You can find the tool here on GitHub: [https://github.com/RemiFabre/WickedLines](https://github.com/RemiFabre/WickedLines)**

This post has three goals:
-   Briefly describe the statistical methodology used by the tool.
-   Share some of the early results it has uncovered so far.
-   Ask if this type of analysis is useful to the community.

---
## The Statistical Toolkit

To find "wicked lines," the tool combines several key metrics:

*   **Reachability ("If Wants %"):** This calculates the probability of reaching a position assuming one player actively tries to get there. It answers the crucial question, "How often can I realistically get this on the board?" The next time you see a cool trap in a YouTube video, you can use this to measure how often you'll actually get a chance to spring it.

*   **Expected Value (EV):** A metric to judge a position's value, calculated from the win/draw/loss percentages using the simple formula: `EV = (+1 * White Win %) + (0 * Draw %) + (-1 * Black Win %)`. A positive EV favors White; a negative EV favors Black.

*   **Delta EV (ΔEV):** This shows how the `EV` changes after a specific move is played. A large `ΔEV` is the core indicator of a move that significantly outperforms the average result of a position.

*   **Statistical Significance (p-value):** This is a crucial filter. It answers the question: "Could this move's high win rate be due to pure random chance?" A low p-value (typically **< 0.05**) suggests the result is statistically significant and not just a fluke.

*   **Expected ELO Gain / 100 Games:** This metric attempts to bundle all the previous concepts into a single, practical number. It uses the formula: `Reachability % * |ΔEV| * ELO_Factor`, where the `ELO_Factor` is ~8 points on Lichess for an even match.

**A Word of Caution:** It's crucial to understand what this number *doesn't* mean. It is **not** a guarantee that *you* will gain `X` ELO points by playing this line. Instead, it reflects the historical performance of the *current pool of players* within the specified rating bracket. It's an indicator of an opportunity, a sign that players at a certain level may be systematically unprepared for a given move.

The tool operates in two modes: `line` mode analyzes a single, specific variation, providing an enhanced view of the data you'd find in the analysis board. The `hunt` mode, which we'll focus on here, automatically searches the opening tree for these high-value opportunities.

---

## The Results Part 1: High-Value Opening Choices

What are the most profitable opening choices you can make right from the start? I ran a broad hunt on the starting position, looking for high-impact lines for players in the **1400-1800 rating** bracket.

The tool found 134 statistically significant opportunities. Here are the top 10, ranked by their ELO Gain potential.

*(The results below were generated with the following configuration: `Max Depth: 5`, `Min Games: 1000`, `Branch Factor: 4`. Results will vary based on your config!)*

## 1. ELO Gain/100: `+26.85`
- **Line:** `e4 c6` (Caro-Kann Defense)
- **Reachable:** `62.54%`
- **Impact:** Line EV: `-1.7`, ΔEV: `-5.4 (good for Black)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.e4%20c6)**

---

## 2. ELO Gain/100: `+22.63`
- **Line:** `d4 d5 Bg5` (Queen's Pawn Game: Levitsky Attack)
- **Reachable:** `45.75%`
- **Impact:** Line EV: `+11.3`, ΔEV: `+6.2 (good for White)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.d4%20d5%202.Bg5)**

---

## 3. ELO Gain/100: `+22.18`
- **Line:** `e4 e5 f4` (King's Gambit)
- **Reachable:** `42.84%`
- **Impact:** Line EV: `+9.3`, ΔEV: `+6.5 (good for White)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.e4%20e5%202.f4)**

---

## 4. ELO Gain/100: `+20.72`
- **Line:** `e4 e5 d4` (Center Game)
- **Reachable:** `42.84%`
- **Impact:** Line EV: `+8.9`, ΔEV: `+6.0 (good for White)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.e4%20e5%202.d4)**

---

## 5. ELO Gain/100: `+19.88`
- **Line:** `Nf3 d5 c4` (Réti Opening)
- **Reachable:** `36.59%`
- **Impact:** Line EV: `+12.5`, ΔEV: `+6.8 (good for White)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.Nf3%20d5%202.c4)**

---

## 6. ELO Gain/100: `+19.18`
- **Line:** `e4 e5 Nf3 d5` (Elephant Gambit)
- **Reachable:** `39.67%`
- **Impact:** Line EV: `+0.3`, ΔEV: `-6.0 (good for Black)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.e4%20e5%202.Nf3%20d5)**

---

## 7. ELO Gain/100: `+16.67`
- **Line:** `e4 e5 Nf3 f5` (Latvian Gambit)
- **Reachable:** `39.67%`
- **Impact:** Line EV: `+1.0`, ΔEV: `-5.3 (good for Black)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.e4%20e5%202.Nf3%20f5)**

---

## 8. ELO Gain/100: `+14.14`
- **Line:** `c4 e5 g3` (no name)
- **Reachable:** `34.57%`
- **Impact:** Line EV: `+11.1`, ΔEV: `+5.1 (good for White)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.c4%20e5%202.g3)**

---

## 9. ELO Gain/100: `+10.86`
- **Line:** `e4 e5 Bc4 Nf6 d4` (Bishop's Opening: Ponziani Gambit)
- **Reachable:** `14.58%`
- **Impact:** Line EV: `+15.0`, ΔEV: `+9.3 (good for White)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.e4%20e5%202.Bc4%20Nf6%203.d4)**

---

## 10. ELO Gain/100: `+9.03`
- **Line:** `d4 d5 Nf3 Nc6 c4` (no name)
- **Reachable:** `9.81%`
- **Impact:** Line EV: `+18.9`, ΔEV: `+11.5 (good for White)`
- **Significance (p-value):** `<0.001`
- **[Analyze on Lichess](https://lichess.org/analysis/pgn/1.d4%20d5%202.Nf3%20Nc6%203.c4)**

The full report with all 134 lines can be found here:
**[Full Report for Start Position Hunt](https://github.com/RemiFabre/WickedLines/blob/main/hunt_results/start_pos_ratings-1400-1600-1800_speeds-blitz-rapid-classical_MD-5_MG-1000_BF-4.md)**

### Analysis: The Asymmetric Advantage

A clear pattern emerges from these results: lines that create an **asymmetric preparation battle** are incredibly effective.

The **Caro-Kann** is a perfect example. If a player commits to playing the Caro-Kann against `1. e4`, they will get to play it in over **62%** of their games as Black. Their preparation is highly efficient. The average `1. e4` player, however, faces the Caro-Kann in a much smaller fraction of their games (**7%**) and has to be prepared for many other responses. This discrepancy gives the Caro-Kann player a significant theoretical and practical advantage, which is reflected in its high ELO Gain score.

The **King's Gambit** (`1. e4 e5 2. f4`) is another excellent example. While it may not be considered top-tier at the highest levels, for the 1400-1800 bracket, it's a deadly weapon. White immediately forces the game into sharp, tactical territory where they are likely far more prepared than their opponent. This tool is useful at quantifying this kind of practical advantage that might be missed by looking only at high level theory.

---

## The Results Part 2: The In-Line Opportunity

The tool is also good at finding specific, surprising moves within an established opening. I ran a separate, more focused hunt on the **Ruy Lopez** (`1. e4 e5 2. Nf3 Nc6 3. Bb5`).

The analysis immediately flagged `3... f5`, the **Schliemann Defense**, as the top opportunity for Black.

Here, the `ΔEV` of **-13.6** is massive. After `3. Bb5`, White enjoys a clear statistical edge (+7.4). By playing the aggressive Schliemann, Black not only equalizes but completely flips the Expected Value to **-6.2** in their favor. With over a million games played, the `<0.001` p-value confirms this is a real, exploitable pattern.

What makes this so potent is the preparation imbalance. A Black player can choose to specialize in this line, getting to play it in about **9.5%** of their games. The average White Ruy Lopez player, however, will only encounter the Schliemann in a tiny **0.43%** of their games. They are almost guaranteed to be less prepared.

The full analysis for this line and other opportunities found within the Ruy Lopez can be found in the report here:
**[Full Report for Ruy Lopez Hunt](https://github.com/RemiFabre/WickedLines/blob/main/hunt_results/e4_e5_Nf3_Nc6_Bb5_Ruy_Lopez_ratings-1400-1600-1800_speeds-blitz-rapid-classical_MD-8_MG-1000_BF-4.md)**

---
## What Next?

I see two main uses for a tool like this:
1.  **Building a Repertoire:** Using data to choose main lines that offer a statistical edge and a practical preparation advantage.
2.  **Finding Counter-Weapons:** Analyzing common openings you struggle against (like the King's Gambit, for me) to find high-performing, statistically-backed responses.

This kind of analysis is new to me, and I'm curious to hear if it's useful to others. I'm happy to run the `hunt` command on requested openings and share the results in future posts. What lines are you curious about? What surprising weapons have you found in your own games? Let me know in the comments.