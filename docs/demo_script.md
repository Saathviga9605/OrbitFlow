# Three-minute demo script

Open the UI full screen. Chapter numbers are on the left rail.

**0:00 Hero (20 s).** "One satellite, 19 areas, four beams, ten milliseconds to choose. In a disaster, the people who most need a link compete with everyone else. These are beams our AI actually chose, in simulation."

**0:20 Chapter 1, three ways to choose (30 s).** Let it play. "A fixed rotation drowns busy areas. A simple scheduler looks fast but forgets quiet ones: 20% of time-critical data arrives late. Ours gets that to 0.6% over 100 test runs of a recorded pass, at the same throughput. The cost is twice the beam switching."

**0:50 Chapter 2, prediction (15 s).** "Forecasting cut error by 71% when demand ramps up, and only 2% when it jumps from nothing. No forecast sees what gives no warning."

**1:05 Chapter 4, flood (45 s).** Click the chips in order. Say first: "This is a test scenario on a recorded satellite pass."
- *Forecast alert, slot 18:* "The system flags the surge ten slots before anyone declares an emergency."
- *Emergency declared:* "Only Safety and the Supervisor are told. Each agent knows only part of the picture."
- *Cap arrives:* "A hypothetical power limit reaches Policy only. It trims proposals before they transmit, and logs a quote it has verified against the source."
- Open the stress test: "Here we deliberately inject 50 watts. It executes at 22. This is a controlled test, not something from the flood. Our AI does propose 50 watts unprompted, in about 0.3% of decisions, which is why the check stays."

**1:50 Chapter 5, evidence (30 s).** Point at the stress table. "Late data falls in every row. Now look at delay: when capacity is scarce, we're slower. We protect deadlines by making the average wait longer. We also found the agents' apparent 9 ms cost wasn't computing, which takes 1.4 ms. It was a design flaw in always-on emergency beams, and fixing it brought delay back down."

**2:20 Chapter 6, lab (25 s).** Move fade, then the limit. "Rain hurts more than a loose limit. But regulators limit power reaching the ground, so we applied a real ITU-R limit. Depending on antenna gain, emergency service stays at 95% or falls to 45%. That's indicative, and it tells us the most valuable number still to measure."

**2:45 Chapter 7, rulebook (15 s).** Pick the exemption question. "It searches 63 evidence documents, and when they don't support a claim, it says so."

## Likely questions

- **Is this real satellite data?** Offline dataset exports for geometry and channel. No live satellite, and no live Sionna. Traffic for training is generated to match the dataset's levels.
- **How robust is 0.6%?** 100 paired runs, 5 trained models, all better than Reactive. On a second dataset it's 2.0% vs 13.7%. All share one pass geometry, so other orbits are untested.
- **Where does it lose?** Average delay under scarce capacity, for example 36 vs 26 ms at 150% traffic. It also switches beams twice as often, and the twin doesn't charge for switching.
- **Why no LLM?** Time-critical safety decisions should be predictable and auditable. Decisions take about 1.4 ms.
- **Do the agents help emergency users?** They guarantee constraints and keep emergency deadlines. In the flood they deliver slightly less total emergency data than no agents (94% vs 96%). A mode serving more exists, at much higher delay for everyone else.
- **Is it compliant with ITU rules?** We make no such claim. The 22 W is hypothetical. The SF.358 study is indicative: our 20 GHz carrier is just outside its listed bands, and transmit gain is assumed.
- **Are the radio parameters validated?** The equations are tested. Values such as antenna gain are provisional, await engineering review, and we show how results move with them.
- **Does forecasting matter?** It cuts delay in some traffic, but not clearly because of ramps: the gain on gradual surges is negligible. We report that as unresolved.
- **Did PPO add anything?** Yes: delay falls from about 32 to 16 ms against the clone on the recorded pass. PPO from scratch also works, so cloning is optional.
- **Is the knowledge evidence solid?** Quotes are verified verbatim, but nothing has had human or legal review. It has no Radio Regulations text, 3GPP or O-RAN documents.

## Live features

Start the server first: `python -m uvicorn dashboard.api:app --port 8000`, then open http://localhost:8000 (or keep the preview on 4173, which forwards to it). Without the server, the game and recorded content still work; the "Ask anything" box and "Run it live" button stay disabled.

**Game (Your turn):** hand a judge the mouse. Scores use the same equations as the Python twin. Note that the player sees exact backlogs and skips the signalling duty, so a win is possible and is not a claim about real operation.
