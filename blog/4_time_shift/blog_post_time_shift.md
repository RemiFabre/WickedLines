# The Shape of Time: How Openings Evolve from Blitz to Classical

I had a dream that the relationship between a player's Elo and the time on their clock was simple and that I could show it graphically as a clean, predictable shift.

I was (very) wrong. But what I found is fascinating.

The following plots were generated with **WickedLines** (contributions welcome), an open-source tool I've been developing:
https://github.com/RemiFabre/WickedLines

The newest feature allows for a direct comparison of an opening's performance across different time controls: Blitz, Rapid, and Classical. For each opening, we get four plots that tell a different part of the story.

![plots/e4_c6_blitz_rapid_classical/e4_c6_blitz_rapid_classical_performance.png](plots/e4_c6_blitz_rapid_classical/e4_c6_blitz_rapid_classical_performance.png)
![plots/e4_c6_blitz_rapid_classical/e4_c6_blitz_rapid_classical_popularity.png](plots/e4_c6_blitz_rapid_classical/e4_c6_blitz_rapid_classical_popularity.png)
![plots/e4_c6_blitz_rapid_classical/e4_c6_blitz_rapid_classical_reachability.png](plots/e4_c6_blitz_rapid_classical/e4_c6_blitz_rapid_classical_reachability.png)
![plots/e4_c6_blitz_rapid_classical/e4_c6_blitz_rapid_classical_surprise.png](plots/e4_c6_blitz_rapid_classical/e4_c6_blitz_rapid_classical_surprise.png)

The charts were generated for the following openings:

#### 1.e4 Openings
*   **Sicilian Defense**: `e4 c5`
*   **French Defense**: `e4 e6`
*   **Caro-Kann Defense**: `e4 c6`
*   **Scandinavian Defense**: `e4 d5`
*   **Alekhine's Defense**: `e4 Nf6`
*   **Modern Defense**: `e4 g6`
*   **Italian Game**: `e4 e5 Nf3 Nc6 Bc4`
*   **Ruy López**: `e4 e5 Nf3 Nc6 Bb5`
*   **Vienna Game**: `e4 e5 Nc3`
*   **Philidor Defense**: `e4 e5 Nf3 d6`
*   **Pirc Defense**: `e4 d6 d4 Nf6 Nc3 g6`
*   **Scotch Game**: `e4 e5 Nf3 Nc6 d4`
*   **King's Gambit**: `e4 e5 f4`

#### 1.d4 Openings
*   **Dutch Defense**: `d4 f5`
*   **Queen's Gambit**: `d4 d5 c4`
*   **Queen's Gambit Accepted**: `d4 d5 c4 dxc4`
*   **Slav Defense**: `d4 d5 c4 c6`
*   **London System**: `d4 d5 Bf4`
*   **King's Indian Defense**: `d4 Nf6 c4 g6`
*   **Nimzo-Indian Defense**: `d4 Nf6 c4 e6 Nc3 Bb4`
*   **Grünfeld Defense**: `d4 Nf6 c4 g6 Nc3 d5`
*   **Catalan Opening**: `d4 Nf6 c4 e6 g3`
*   **Modern Benoni**: `d4 Nf6 c4 c5 d5 e6`

#### Other Openings
*   **English Opening**: `c4`
*   **Réti Opening**: `Nf3 d5 c4`

## How to Read the Graphs:

*   **Expected Elo Gain / 100 Games**: The expected rating point change from playing this line 100 times.
*   **Average White Elo Gain**: A baseline showing average performance from move 1.
*   **Reachability %**: Your chance to get this opening on the board if you try.
*   **Popularity %**: How often this opening is seen in all games.
*   **Theory Advantage**: Reachability / Popularity. A measure of surprise value and preparation efficiency.

**Note:** I removed the 2500+ Elo bracket because it had a low amount of games (especially in classical) and the values often were non-significant statistically and extreme in value.

**Note:** The charts are seen from the perspective of the player that made the last move of the opening. So for the Caro-Kann (e4 c6), high values are good for Black. For the English (c4) high values are good for White.



---

## My Prediction (and Why It Was Wrong)

My initial hypothesis was straightforward: a game between stronger players with less time should be somewhat similar to a game between weaker players with more time. I expected the discussion to be about diminishing returns for each extra minute of time and the trade-off between intuition vs calculation.


Graphically, I expected to see a simple shift along the x-axis. I thought I could take a performance curve from Blitz, slide it to the left, and have it roughly match the curve for Rapid. Slide it again, and it would match Classical.

This turned out to be completely wrong. Here is what I observed across the ~25 openings I plotted.

### Observation 1: The "Maximizing Effect" of Time

One pattern was almost universally true: **if an opening is good in practice, it gets better with more time. If it's bad, it gets worse.**

A few examples:

![plots/shift/e4_e5_nf3_nc6_bb5_blitz_rapid_classical_performance.png](plots/shift/e4_e5_nf3_nc6_bb5_blitz_rapid_classical_performance.png)
![plots/shift/e4_e5_nf3_d6_blitz_rapid_classical_performance.png](plots/shift/e4_e5_nf3_d6_blitz_rapid_classical_performance.png)



On the surface, this might seem trivial, but I think it's profound, and I'm not sure I'm able to understand it fully. It seems that from an opening position, increasing the time on the clock tends to increase the practical advantage of the player who is already better off.

One might offer a simple explanation: "This makes sense. If a position holds a genuine, objective advantage, more time allows a player to calculate more precisely and maximize it." But I think this is a lazy explanation, and possibly wrong.

To emphasize why this is non-trivial, let's imagine for a second that the curves were inverted, that performance was more extreme in Blitz than in Classical. It would be very easy for me to give a convincing explanation: 'Of course! In Blitz, once a player has an advantage, the defender doesn't have enough time to dismantle it. The chaos of lower time controls naturally exacerbates any edge.'

That explanation sounds perfectly plausible, doesn't it? Yet we observe the exact opposite. This is why I want to be very careful in providing an intuitive explanation for what we're seeing.

Could this mean that converting a practical advantage is fundamentally harder (requires more time) than stabilizing the game?

It is important to note that:
*   These observations are based on opening data. We might see a different picture if we were to study specific middle-game states.
*   These observations are based on human performance for Elos below ~2300. We know that draw rates increase significantly at higher levels and that there is a lot of skill expression in the game above 2300. These findings are about the nature of *humans playing chess*, not necessarily about the objective nature of the game itself.

I'm very interested in having your opinion on this.

### Observation 2: The Inverted Shift

I predicted a shift, and a shift *does* appear in many openings. The only problem is that the direction is ... the complete inverse of what I expected!

Let's take the King's Gambit as a practical example. This opening is king around 1500-1700 Elo, performing poorly at very low and very high levels. My intuition was that if a 2100-rated player in a Classical game can handle the KG, a Blitz player would need to be even higher rated (e.g., 2300) to do the same with less time.

![plots/shift/e4_e5_f4_blitz_rapid_classical_performance.png](plots/shift/e4_e5_f4_blitz_rapid_classical_performance.png)

The data shows the opposite. The entire performance curve is shifted to the left in faster time controls. A player seems to "master" handling the King's Gambit at a *lower* Elo in Blitz than they do in Classical. I find this fascinating, and I see two potential explanations:

1.  The Maximizing Effect Again: Time might help maximize an existing advantage. Since you have less time in Blitz, the potential advantage of the King's Gambit is less pronounced.
2.  The Experience Factor: Blitz players simply face the King's Gambit many more times than Classical players because they play so many more games. For openings where success relies on surprising an unprepared opponent, their effectiveness is naturally reduced against a massive pool of experienced Blitz players. One could argue this is especially true for openings that rely on traps, which lose their potency once a player is aware of them.

This inverted shift is clear in openings like the Dutch Defense, the Philidor, and even the Ruy Lopez (which has a rare double-dome shape).

![plots/shift/d4_f5_blitz_rapid_classical_performance.png](plots/shift/d4_f5_blitz_rapid_classical_performance.png)

![plots/shift/e4_e5_nf3_d6_blitz_rapid_classical_performance.png](plots/shift/e4_e5_nf3_d6_blitz_rapid_classical_performance.png)




### Observation 3: The "No-Shift" Openings

Finally, there are openings where this shift is almost non-existent, even though the maximizing effect of time is still visible. The two clearest examples are the **Sicilian Defense** and the **Caro-Kann Defense**.

![plots/no_shift/e4_c5_blitz_rapid_classical_performance.png](plots/no_shift/e4_c5_blitz_rapid_classical_performance.png)

![plots/no_shift/e4_c6_blitz_rapid_classical_performance.png](plots/no_shift/e4_c6_blitz_rapid_classical_performance.png)

In both cases, the performance curves for Blitz, Rapid, and Classical are remarkably aligned. It's interesting that both are Black's responses to 1.e4, and both involve the c-pawn. Perhaps there's something fundamental about these structures that stabilizes the nature of the game across time controls in a way I'm unable to fully understand. If you have a theory for this, I'd love to hear it. Mine is that this structure allows for both bishops to be developped more often than in other openings.


### Next Steps & How to Dig Deeper

It's possible that I am reading too much into this and that the "Experience Factor" of Blitz players is the single most important explanation for these effects. To truly test these hypotheses and separate the different variables at play, we would need a more in-depth analysis.

Here are some ideas for future research, both for this project and for anyone interested in exploring the data.

#### 1. Isolating Opening Knowledge with Engine Analysis

A bad performance might be due to a subtle strategic weakness in the opening, or simply a player blundering into a well-known trap.

We could untangle these factors by using a chess engine like Stockfish. The methodology would be:
1.  Analyze a large sample of games for a given opening.
2.  Filter out all games where a player makes a significant blunder (e.g., losing more than a pawn of value) within the first 5-10 moves.
3.  Re-plot the performance curves using only the remaining population of players who demonstrated they "knew" the opening enough not to fall for an immediate trap.

This would allow us to see if the time-control shifts persist even when basic opening knowledge is equalized, giving us a clearer view of how time affects play, independent of preparation.

#### 2. Modeling Player-Specific Opening Expertise

Instead of looking at an entire Elo bracket as a monolith, we could model expertise on an individual level. This would involve processing the entire Lichess database to track how many times each player has played a specific opening. We could then plot performance not just against Elo, but against an "Experience Score" for that line.

This is a massive undertaking, far beyond the scope of the simple opening API calls my tool currently does. From a research perspective, however, it would be incredibly interesting.

#### 3. Analyzing a Middle-Game Position

To better isolate the effect of time on play from the variable of opening preparation, we could find a complex middle-game position that is reached a significant number of times through different transpositions.

Analyzing the performance from that position across different time controls would give us a purer look at how time pressure affects strategic and tactical decision-making, while reducing the impact of specific opening theory.

This is actually feasible with the current tool. **If anyone has a suggestion for a suitable FEN string for such a position, I would love to test it.**

---

It's not practical to post all the plot images here, but you can find a gallery of every chart I generated in the project repository:

**https://github.com/RemiFabre/WickedLines/tree/main/plots**

Hopefully, you find something interesting or useful here for your own openings.

Let this be a snapshot of the complex and fascinating behavior of openings in practice!

Best,

PS: Let's end this blog with a chart. Because I love charts and I have no idea what is going on with the modern defense:

![plots/nonsense/e4_g6_blitz_rapid_classical_performance.png](plots/nonsense/e4_g6_blitz_rapid_classical_performance.png)
