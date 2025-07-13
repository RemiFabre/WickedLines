# The Shape of Time: How Openings Evolve from Blitz to Classical

I had a dream that the relationship between a player's Elo and the time on their clock was simple and that I could show it graphically as a clean, predictable shift.

I was very (very) wrong. But what I found is fascinating.

The following plots were generated with **WickedLines** (contributions welcome), an open-source tool I've been developing. The newest feature allows for a direct comparison of an opening's performance across different time controls: Blitz, Rapid, and Classical. For each opening, we get four plots that tell a different part of the story.


### How to Read the Graphs:

*   **Expected Elo Gain / 100 Games**: The expected rating point change from playing this line 100 times. Positive is good for White.
*   **Average White Elo Gain**: A baseline showing White's average performance from move 1.
*   **Reachability %**: Your chance to get this opening on the board if you try (as White).
*   **Popularity %**: How often this opening is seen in all games.
*   **Theory Advantage**: Reachability / Popularity. A measure of surprise value and preparation efficiency.

(Insert 4 charts, Caro maybe?)

These charts were generated for the following openings:
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

Note: I removed the 2500+ ELO bracket because it had a low amount of games (especially in classical) and the values often were non significant statistically and extreme in value.

---

### My Prediction (and Why It Was Wrong)

My initial hypothesis was straightforward: a stronger player with less time should, on average, play like a slightly weaker player with more time. There's a point of diminishing returns for each extra minute you think, but the general effect should be clear.

Graphically, I expected to see a simple shift along the x-axis. I thought I could take a performance curve from Blitz, slide it to the right, and have it roughly match the curve for Rapid. Slide it again, and it would match Classical.

This turned out to be completely wrong. Here is what I observed across the ~25 openings I plotted.

### Observation 1: The "Maximizing Effect" of Time

One pattern was almost universally true: **if an opening is good in practice, it gets better with more time. If it's bad, it gets worse.**

A few examples:
[e4_e5_nf3_d6_blitz_rapid_classical_performance.png] and [e4_e5_nf3_nc6_bb5_blitz_rapid_classical_performance.png]


On the surface, this might seem trivial, but I think it's profound, and I'm not sure I'm able to understand it fully. It means that from an opening position, increasing the time on the clock tends to increase the practical advantage of the player who is already better off.

One might offer a simple explanation: "This makes sense. If a position holds a genuine, objective advantage, more time allows a player to calculate more precisely and maximize it." But I think this is a lazy explanation, and possibly wrong.

To emphasize why this is non-trivial, let's imagine for a second that the curves were inverted—that performance was more extreme in Blitz than in Classical. It would be very easy for me to give a convincing explanation: 'Of course! In Blitz, once a player has an advantage, the defender doesn't have enough time to dismantle it. The chaos of lower time controls naturally exacerbates any edge.'

That explanation sounds perfectly plausible, doesn't it? Yet we observe the exact opposite. This is why I want to be very careful in providing an intuitive explanation for what we're seeing.

Could this mean that converting a practical advantage is fundamentally harder (requires more time) than stabilizing the game?

It is important to note that:

    These observations are based on opening data. We might see a different picture if we were to study specific middle-game states.

    These observations are based on human performance for Elos below ~2300. We know that draw rates increase significantly at higher levels, and these findings are about the nature of humans playing chess, not necessarily about the objective nature of the game itself.

I'm very interested in having your opinion on this.

### Observation 2: The Inverted Shift

I predicted a shift, and a shift *does* appear in many openings. The only problem is that the direction is ... the complete inverse of what I expected!

Let's take the King's Gambit as a practical example. This opening is king around 1500-1700 Elo, performing poorly at very low and very high levels. My intuition was that if a 2100-rated player in a Classical game can handle the KG, a Blitz player would need to be even higher rated (e.g., 2300) to do the same with less time.

[e4_e5_f4_blitz_rapid_classical_performance.png]

The data shows the opposite. The entire performance curve is shifted to the left in faster time controls. A player seems to "master" handling the King's Gambit at a lower Elo in Blitz than they do in Classical. I find this fascinating, and I see two potential explanations:

    The Maximizing Effect Again: As we saw, time helps maximize an existing advantage. Since you have less time in Blitz, the potential advantage of the King's Gambit is less pronounced.

    The Experience Factor: This seems more significant. Blitz players simply face the King's Gambit many more times than Classical players because they play so many more games. For openings where success relies on surprising an unprepared opponent, their effectiveness is naturally reduced against a massive pool of experienced Blitz players. One could argue this is especially true for openings that rely on traps, which lose their potency once a player is aware of them.

This inverted shift is clear in openings like the Dutch Defense, the Philidor, and even the Ruy Lopez (which has a fascinating double-dome shape).

### Observation 3: The "No-Shift" Openings

Finally, there are openings where this shift is almost non-existent, even though the maximizing effect of time is still visible. The two clearest examples are the **Sicilian Defense** and the **Caro-Kann Defense**.

[no shift folder]

In both cases, the performance curves for Blitz, Rapid, and Classical are remarkably aligned. It's interesting that both are Black's responses to 1.e4, and both involve the c-pawn. Perhaps there's something fundamental about these structures that stabilizes the nature of the game across time controls in a way I'm unable to fully understand. If you have a theory for this, I'd love to hear it. Mine is that this structure allows for both bishops to be developped more often than in other openings.

---

It's not practical to post all the plot images here, but you can find a gallery of every chart I generated in the project repository:

**https://github.com/RemiFabre/WickedLines/tree/main/plots**

Hopefully, you find something interesting or useful here for your own openings.

Let this be a snapshot of the complex and fascinating behavior of openings in practice!

Best,