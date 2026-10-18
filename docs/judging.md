# Judging and Demos

Scoring as set for the event. If this page ever differs from the organizers' brief, the brief governs. ✅

## Scoring

| Weight | Criterion | What judges look for |
|---|---|---|
| 25% | **Edge-native value** | Why is this better, or only possible, on-device? |
| 20% | **Technical execution** | Reliability, integration quality, local operation |
| 20% | **Originality** | A distinct insight, not another generic chatbot |
| 15% | **Real-world usefulness** | A clear user, a real need, a plausible next step |
| 10% | **Performance / efficiency** | Latency, memory, endurance, resource awareness |
| 10% | **Demo quality** | A concise, credible offline proof |

## The first question

Every finalist gets this question: **"Why should this not simply be a cloud API call?"**

Prepare an answer that names a specific constraint. Examples: the network is unavailable, the data is sensitive, the reaction must happen in under a second, or the marginal cost has to stay flat at scale. Being on-device is not an answer by itself.

## Bonus awards

- **Fastest Agent** — speed of the end-to-end loop
- **Best Tiny Agent** — the best result for the smallest footprint

Record the numbers that support these claims. See [`runtimes.md`](runtimes.md) for `geniex-bench` and [`developer-guide.md` §10](developer-guide.md#10-measuring-performance).

## Demo format

- Two minutes per team, plus one judge question. ✅ (brief)
- The network is removed for the final demo. Your demo must run with it off. ✅
- Show the local log of decisions as proof.
- Prepare a visible timer and a backup recording. ✅ (brief's demo-discipline requirements)

## What to measure and show

| Metric | How | Why it matters |
|---|---|---|
| Time-to-first-token | `geniex-bench`, or a timed streamed request to the server | Responsiveness |
| Decode tokens/s | `geniex-bench`, or tokens over time from a streamed request | Endurance and feel |
| Peak memory | `free -h` or `top` during a run | Footprint |
| Decision-gate latency | Timed decisions on the board: Path A on the CPU is about 4.5 s per state (three questions) | Shows whether the gate fits your observation rate. Model-card latencies are for other hardware. |
| Network-off run | Demo with Ethernet and Wi-Fi unplugged | The core claim |
| Decision log | Local file with timestamps | Proof the loop ran |
