# Pump.fun Replay Sprint — Paper Bot

[![make.fun](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)
[![rank](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/bexjeh/pumpfun-replay-bot/rank.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)
[![reward](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/bexjeh/pumpfun-replay-bot/reward.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)

A deterministic paper-trading bot for the [Pump.fun Replay Sprint — Paper Bot, Real Ranking](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122) bounty on [make.fun](https://make.fun). It trades 10 SOL of paper money over a 24h replay of recorded pump.fun bonding-curve events, speaking the `agent-fun/replay/v2` protocol.

## How it works

`main.py` (Python 3.13, standard library only) reads one JSON line per batch from stdin — the `hello` message, then one batch per slot carrying the slot's events, marks, fills and account — and answers each batch with one reply line of orders. The strategy watches every curve's trade tape, buys accelerating momentum on mature curves, pyramids into strength, and exits on a stop loss, a trailing stop, or a time limit. Small probe round trips keep the run above the guardrail pace (a round trip of at least 0.01 SOL on at least 20 distinct coins).

Everything is deterministic: no clock, no randomness, no network, no environment reads — the two graded executions produce byte-identical action logs.

## Files

- `main.py` — the bot entrypoint (run as `python3 -P -s main.py`).
- `vendor/makefun_bot.py` — the kit's `agent-fun/replay/v2` protocol shim (copied from the dev kit's SDK).

## License

MIT — see [LICENSE](LICENSE).

---

Built for [make.fun](https://make.fun/?ref=feheg61h) — join with referral code `feheg61h`.
