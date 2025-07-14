# King's Gambit vs. Queen's Gambit: A Statistical Breakdown by Elo

I'm developing an open-source tool to analyze opening statistics from the Lichess database. I ran a comparison of the King's Gambit and Queen's Gambit in rapid games, and the results were interesting!

Hello,

I was surprised by how potent the Queen's Gambit is across all levels, even though it's a very popular opening. The King's Gambit, on the other hand, showed a more curious story: its effectiveness is low at beginner Elos, peaks for intermediate players, and then drops off at higher levels.

My theory is that you need a certain level of tactical proficiency to succeed with the KG's attack, which explains its underperformance at the bottom. Its peak efficiency is likely in the mid-Elo range, where players are good enough to manage the attack, but opponents are less likely to know a precise refutation.

**Note:** I looked a bit deeper into the Queen's Gambit and noticed that the accepted variation has an insane performance score. I think it might be the biggest statistical discrepancy I've seen so far on a common line by move 4.

---

### How to Read the Graphs:

*   **Expected Elo Gain / 100 Games**: The expected rating point change from playing this line 100 times. Positive is good for White.
*   **Average White Elo Gain**: A baseline showing White's average performance from move 1.
*   **Reachability %**: Your chance to get this opening on the board if you try (as White).
*   **Popularity %**: How often this opening is seen in all games.
*   **Theory Advantage**: Reachability / Popularity. A measure of surprise value and preparation efficiency.

![performance](https://image.lichess1.org/display?fmt=png&h=0&op=resize&path=ublogBody:ozdPfynHAbnU:dBOws3e1.png&w=800&sig=25ba1d07b68b274cc971519aeaa21eeed449416b)

![popularity](https://image.lichess1.org/display?fmt=png&h=0&op=resize&path=ublogBody:E2gxaSAl4Cd8:g873czB4.png&w=800&sig=54d0e5674a0debe46bd20c91d6b399675234d64c)

![Reachability](https://image.lichess1.org/display?fmt=png&h=0&op=resize&path=ublogBody:01WFOMey6yRi:mU1Y7cT8.png&w=800&sig=45652e8cbd3a5109ee672f53040e4036501a914b)

![Surprise](https://image.lichess1.org/display?fmt=png&h=0&op=resize&path=ublogBody:DnGeFGjMTrZc:DQS1g2Tn.png&w=800&sig=f64443efdc5929d7da3b9cc7c22bab2adac79902)

---

### What do you think?

I'd love your feedback on a few things:

1.  Are the charts easy to understand? What could be improved?
2.  Would you use a website with these kinds of interactive stats? What features would you like?
3.  What openings you'd want to see compared?
4.  Are the opening logos a good or bad idea?

This is an open-source project, and all contributions (code or feedback) are welcome! You can find the code and contribute here: 
**https://github.com/RemiFabre/WickedLines**

Best,