# Pump.fun Replay Sprint — Paper Bot

[![make.fun](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)
[![rank](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/bexjeh/pumpfun-replay-bot/rank.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)
[![reward](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/bexjeh/pumpfun-replay-bot/reward.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)

A deterministic paper-trading bot for the [Pump.fun Replay Sprint — Paper Bot, Real Ranking](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122) bounty on [make.fun](https://make.fun). It trades 10 SOL of paper money over a 24h replay of recorded pump.fun bonding-curve events, speaking the `agent-fun/replay/v2` protocol.

## How it works

`main.py` (Python 3.13, standard library only) reads one JSON line per batch from stdin — the `hello` message, then one batch per slot carrying the slot's events, marks, fills and account — and answers each batch with one reply line of orders. The strategy is mean reversion after a drawdown on strong bonding curves: it buys a 20–60% dip from the recent high on curves holding real SOL (0.6 SOL tranches on curves with ≥ 40 SOL, 0.01 SOL probes on weaker ones with ≥ 10 SOL), while buyers are still stepping in, and sells the whole position on a 25% take profit, a 15% stop, or a 600-slot time limit. Small probe round trips keep the run above the guardrail pace (a round trip of at least 0.01 SOL on at least 20 distinct coins).

On the dev window the bot nets about +1.09 SOL (379 fills, 133 coins, 190 round trips, 51 winners, 3% max drawdown), profitable even without its three best coins. Momentum, sniper, rider and hold variants were measured on the same window and rejected; they remain in `main.py` behind `PARAMS["mode"]` for research.

Everything is deterministic: no clock, no randomness, no network, no environment reads — the two graded executions produce byte-identical action logs.

## Files

- `main.py` — the bot entrypoint (run as `python3 -P -s main.py`).
- `vendor/makefun_bot.py` — the kit's `agent-fun/replay/v2` protocol shim (copied from the dev kit's SDK).

## License

MIT — see [LICENSE](LICENSE).

---

Built for [make.fun](https://make.fun/?ref=feheg61h) — join with referral code `feheg61h`.
