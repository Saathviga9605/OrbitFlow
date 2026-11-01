# Three-minute demo script

Open the UI at full screen. Chapter numbers are on the left rail.

**0:00 Hero (20 s).** "One satellite, 19 cells, 4 beams, 10 milliseconds. During a flood, the people who most need a link compete with everyone else under the footprint. These beams are the ones our policy really chose."

**0:20 Chapter 1, three schedulers (30 s).** Let it play. "A fixed rotation drowns the busy cells. A greedy scheduler looks excellent on delay, but on a real pass it leaves 20.7% of cell-slots past their real-time deadline. BRIDGE, which never trained on that pass, matches its throughput and gets that down to 0.7%. The price is more beam switching."

**0:50 Chapter 2, prediction (20 s).** "We forecast three slots ahead. This cuts error at ramps by 71%, and by only 2% on abrupt jumps. A forecaster cannot see what gives no warning, and we report that."

**1:10 Chapter 4, flood relief (60 s).** Click the chips in order.
- *Forecast alert:* "The system flags the surge ten slots before anyone declares an emergency."
- *Emergency declared:* "Only Safety and the Supervisor are told. Network is still optimising without knowing."
- *Cap arrives:* "A simulated regulator notice reaches Policy only. BRIDGE proposes 24.9 W on border cell 16 and the cap is 22. It is repaired before transmission, with a verified citation. Policy then searches for an emergency exemption, finds none, and says so."

**2:10 Chapter 5, cost table (20 s).** "Agents removed all 22 cap breaches and raised emergency service, but delay went from 14 to 23 ms. Compliance has a price, and we measured it."

**2:30 Chapter 6, what-if lab (20 s).** Drag fade to 12 dB, then move the cap. "Each square is a full run. Emergency service falls with rain and barely moves with the cap, and at 12 dB a human is called in."

**2:50 Chapter 8, ledger (10 s).** "This page lists what is real, simulated and assumed. Every number reproduces from one script."

## Likely questions

- **Is the data real?** The pass geometry and channel are. Training demand is synthetic and calibrated to it. The flood scenario is simulated.
- **Where is the LLM?** There isn't one. Agents are deterministic so that decisions are auditable. A model should not have authority over a legal limit.
- **Is the RAG on real law?** Not yet. The engine works, but its corpus is simulated. The gap candidate is a gap in our corpus, not a finding about the law.
- **Did PPO matter?** Modestly. Most performance comes from cloning a good heuristic; PPO then lowers delay substantially on the real pass (30.8 ms for the heuristic, 14.1 ms for BRIDGE).
- **How robust is the 0.7%?** It comes from one real pass. On block traffic, the closest synthetic match over 18 episodes, RT misses are 0.6% against Reactive's 19.5%.
