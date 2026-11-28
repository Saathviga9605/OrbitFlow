# Three-minute demo script

Open the UI full screen. Chapter numbers are on the left rail. All numbers are v3 (58 cells, 12 beams, 300 W).

**0:00 Hero (20 s).** "One satellite, 58 areas across three regions, twelve beams, ten milliseconds to choose. In a disaster, the people who most need a link compete with everyone else. These are beams our AI actually chose, in simulation."

**0:20 Chapter 1, three ways to choose (30 s).** Let it play. "A fixed rotation drowns busy areas. Most late data here comes from areas with no line of sight, which no scheduler can reach, so we count only data a beam could have delivered. A simple scheduler delivers 1.35% of that late; ours 1.20%, over 100 test runs of the recorded pass. A hand-written predictive rule does better still, at 1.07%, and we show that too."

**0:50 Chapter 2, prediction (15 s).** "Forecasting cut error by 76% when demand ramps up. On the recorded pass, where demand rises smoothly, simply repeating the last value is more accurate, and we say so."

**1:05 Chapter 4, flood (45 s).** Click the chips in order. Say first: "This is a test scenario on a recorded satellite pass."
- *Forecast alert:* "The system flags the surge before anyone declares an emergency."
- *Emergency declared:* "Only Safety and the Supervisor are told. Each agent knows only part of the picture."
- *Cap arrives:* "A hypothetical power limit reaches Policy only. It trims proposals before they transmit, and logs a quote it has verified against the source."
- Open the stress test: "Here we deliberately inject 150 watts on a border cell. It executes at 22. Unprompted, our AI puts 150 watts or more on one beam in about 11% of decisions, sensible on a busy hotspot, which is exactly why the limit is checked every slot."

**1:50 Chapter 5, evidence (30 s).** "Against the simple scheduler we miss fewer deadlines in 14 of 20 test conditions, tie in 2 and lose in 4: heavier traffic, random bursts and a much worse channel. Average delay is always a little higher, because we put time-critical data first. Without agents, the AI breaks the power limit in 23 slots of the flood; with them, zero."

**2:20 Chapter 6, lab (25 s).** Move fade, then the limit. "Rain hurts more than a loose limit. Regulators limit power reaching the ground, so we applied an ITU-R limit as a guide. With a 30 dBi antenna, emergency service falls from 27% to 15%. That's indicative, and it tells us the most valuable number still to measure."

**2:45 Chapter 7, rulebook (15 s).** Pick the exemption question. "It searches the evidence documents, and when they don't support a claim, it says so."

## Likely questions

- **Is this real satellite data?** Offline dataset exports for geometry, channel and demand: 58 cells, 100 slots. No live satellite, and no live Sionna. Training traffic is generated to match the dataset's levels and its pass-long ramp.
- **Why is total lateness 12–13% for everyone?** Cells have line of sight in only 36% of cell-slots, and without it nothing decodes. About 97% of late data is physically unavoidable, so we lead with the serviceable figure and always show the total.
- **Is your AI the best?** Not in v3. It beats the simple scheduler in most conditions, but a hand-written predictive rule is lower on the recorded pass, and our AI ends close to the rule it was initialised from. We report that and have a retraining plan.
- **Where does it lose?** Heavier traffic (125%, 150%), random bursts, a 6 dB worse channel, and average delay everywhere (1.3–14 ms higher).
- **Why no LLM?** Time-critical safety decisions should be predictable and auditable. Decision plus checks take 2.0 ms on average, 2.7 ms at p99.
- **Do the agents help emergency users?** They guarantee the limit: zero breaches against 23–27 slots for the baselines. They deliver less emergency data than the baselines (22% vs 26–29%), which serve more partly by breaking the limit. The flood cells are often out of line of sight.
- **Is it compliant with ITU rules?** We make no such claim. The 22 W is hypothetical. The SF.358 study is indicative: our 20 GHz carrier is just outside its listed bands, and transmit gain is assumed.
- **Are the radio parameters validated?** The equations are tested. Bandwidth (80 MHz) was chosen by a sweep using baselines only; antenna gain and isolation are provisional and await engineering review.
- **Did PPO add anything?** Little on top of the behaviour clone in the deployed setup (2 of 5 seeds improved). Without the forecast, or from scratch, it improved on all 5 seeds.
- **Is the knowledge evidence solid?** Quotes are verified verbatim, but nothing has had human or legal review. It has no Radio Regulations text, 3GPP or O-RAN documents.

## Live features

Start the server first: `python -m uvicorn dashboard.api:app --port 8000`, then open http://localhost:8000 (or keep the preview on 4173, which forwards to it). Without the server, the game and recorded content still work; the "Ask anything" box and "Run it live" button stay disabled.

**Game (Your turn):** hand a judge the mouse. Scores use the same equations as the Python twin. Note that the player sees exact backlogs and skips the signalling duty, so a win is possible and is not a claim about real operation.
