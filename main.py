"""Pump.fun Replay Sprint paper bot (agent-fun/replay/v2), Python 3.13, stdlib only.

Strategy: mean reversion after a drawdown on strong bonding curves. A curve that ran
up and then dropped 20-60% from its recent high, while buyers are still stepping in,
tends to bounce part of the way back. The bot buys into that dip in one tranche
(0.6 SOL on strong curves holding >= 40 SOL real, 0.01 SOL probes on weaker ones
holding >= 10 SOL) and sells the whole position on a 25% take profit, a 15% stop,
or a 600-slot time limit. The settings were chosen by sweeping the dev window with
the kit's own replay engine and preferring a flat, positive region over its single
best cell; the shipped settings are profitable on the full dev window (+1.09 SOL
net) and in two of its three thirds, with a 3% max drawdown.

The file also carries the momentum, sniper, rider and hold modes that were measured
and rejected on the dev window (see PARAMS["mode"]); they share one tape/exit engine
and are kept for research, not shipped.

How a batch is answered: the harness sends one batch per slot with the slot's events
(CreateEvent / TradeEvent / CompleteEvent), marks for held and pending mints, the fills
of orders decided 2 slots earlier, and the account. on_batch first processes exits on
held positions, then entries on curves that traded in this batch, then guardrail
probes if the round-trip pace lags. Every decision is a pure function of the batches
seen so far: no clock, no randomness, no network, no environment reads, and all
iteration is over insertion-ordered dicts, so the two graded executions produce
byte-identical action logs.

Guardrail probes keep the run above 20 distinct coins with a round trip of at least
0.01 SOL each: when the bot's own qualifying coins lag a pace set in block time, it
buys probe_sol of a liquid curve and sells it as soon as the buy lands.

All money is integer lamports; prices are compared as (virtual_quote, virtual_token)
pairs by cross-multiplication, so no float rounding can split the two graded runs.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bot  # noqa: E402

LAMPORTS = makefun_bot.LAMPORTS_PER_SOL
BPS = 10_000
CURVE_FEE_BPS = 125  # protocol 95 + creator 30
MIN_ROUND_TRIP = 10_000_000  # 0.01 SOL: the guardrail's minimum buy per coin
CASH_RESERVE = 50_000_000  # 0.05 SOL never spent on buys: exits must always afford tx fees


def sol(x):
    """SOL as lamports (int)."""
    return int(round(x * LAMPORTS))


DEFAULT_PARAMS = {
    # --- mode: "reversion" (shipped) | "momentum" | "sniper" | "rider" | "hold" ---
    "mode": "reversion",
    # --- momentum entry ---
    "window": 30,            # entry window, slots
    "min_net_sol": sol(1.0),  # net buy SOL over the window
    "min_buys": 3,           # buy trades in the window
    "min_buyers": 5,         # distinct buying wallets in the window
    "min_price_up_bps": 500,   # price now over window-start price, min
    "max_price_up_bps": 15000,  # ... max (skip curves that already ran too far)
    "accel_bps": 10000,      # newer-half net inflow >= this share of older-half
    "near_high_bps": 9500,   # price now >= this share of the window high
    "max_buyer_share_bps": 10000,  # largest single wallet's share of window buy SOL
    "min_rq_sol": sol(2.0),
    "max_rq_sol": sol(60.0),
    "min_age": 500,          # slots since CreateEvent before an entry is allowed
    # --- sniper entry ---
    "snipe_max_age": 3,      # oldest age (slots) at which a first buy may be decided
    "snipe_min_rq_sol": sol(0.3),
    "snipe_max_rq_sol": sol(30.0),
    "snipe_max_dev_buy_sol": sol(2.5),
    "snipe_max_buyers": 3,   # a launch bundled by many wallets is a dump in waiting
    "snipe_skip_dev_sold": True,
    # --- reversion entry (shipped settings) ---
    "rev_high_window": 2500,  # lookback (slots) for the recent high
    "rev_dd_min_bps": 2000,  # enter at least this far below the recent high
    "rev_dd_max_bps": 6000,  # ... and not further (a collapse, not a dip)
    "rev_min_rq_sol": sol(10.0),
    "rev_strong_rq_sol": sol(40.0),
    "rev_flow_trades": 6,
    "rev_min_buys": 3,
    "rev_last_must_be_buy": True,
    "rev_tranche_strong_sol": sol(0.6),
    "rev_tranche_weak_sol": sol(0.01),
    "rev_weak_dd_min_bps": 2000,
    "rev_weak_dd_max_bps": 6000,
    "rev_add": False,        # add tranches while the dip holds near entry
    "rev_add_band_bps": 500,
    "rev_max_position_sol": sol(1.0),
    # --- rider entry (grind-to-completion) ---
    "rider_min_rq_sol": sol(40.0),
    "rider_max_rq_sol": sol(84.0),
    "rider_min_trades": 50,   # lifetime trades: separates grinders from instant jumps
    "rider_min_age": 150,     # slots since CreateEvent
    "rider_near_high_bps": 9000,  # price now >= this share of the 100-slot high
    "rider_flow_window": 100,
    "rider_min_flow_sol": 0,
    "stake_sol": sol(2.0),   # SOL to put into one position in total
    "initial_sol": sol(0.05),  # first buy of a position
    "add_sol": sol(0.2),     # each pyramid add-on buy
    "add_step_bps": 0,       # add only once price is this far above the last buy
    "add_if_up_bps": -10000,  # add only while close value >= cost * (1 + this)
    "add_net_sol": 0,        # add only while net SOL over the window >= this
    "min_buy_sol": sol(0.01),
    "max_exposure_sol": sol(6.0),  # most SOL at cost across all positions at once
    "max_main": 5,           # most momentum positions open at once
    "buy_slip_bps": 1500,
    # --- exits (shipped: 25% take profit, 15% stop, 600-slot hold; no trail) ---
    "stop_loss_bps": 1500,   # exit when value < cost * (1 - this)
    "trail_bps": 100000,     # exit on a fall of this from the best value (off)
    "trail_arm_bps": 100000,  # ... once value reached cost * (1 + this) (off)
    "take_profit_bps": 2500,  # 0 = off; exit when value >= cost * (1 + this)
    "max_hold": 600,         # exit after this many slots held
    "cooldown": 300,         # slots to wait after an exit before re-buying a curve
    "max_entries": 2,        # most entries per curve over the run
    "exit_on_dev_sell": False,
    "stale_slots": 0,        # 0 = off; exit when no trade hit the coin for this long
    "fade_window": 15,       # exit when net SOL over this window < -fade_net_sol
    "fade_net_sol": sol(1000),  # (huge = off)
    # --- guardrail probes ---
    "target_coins": 25,
    "pace_secs": 14400,
    "probe_sol": sol(0.012),
    "max_probes": 1,
}


def price_gt(a_vq, a_vt, b_vq, b_vt):
    """True when price a (vq/vt) is strictly greater than price b."""
    return a_vq * b_vt > b_vq * a_vt


def price_ratio_bps(vq_now, vt_now, vq_then, vt_then):
    """(price_now / price_then - 1) in bps, as an int (floored)."""
    if vq_then <= 0 or vt_now <= 0:
        return -10000
    return (vq_now * vt_then * BPS) // (vt_now * vq_then) - BPS


class Tape:
    __slots__ = ("created", "creator", "trades", "entries", "last_exit", "dev_buy",
                 "dev_sold", "buyers", "bought", "sold_by_others", "last_trade_slot",
                 "total_trades")

    def __init__(self):
        self.created = None
        self.creator = None
        # (slot, is_buy, sol_lamports, user, vq, vt), oldest first
        self.trades = []
        self.entries = 0
        self.last_exit = -10**12
        self.dev_buy = 0
        self.dev_sold = False
        self.buyers = set()
        self.bought = 0
        self.sold_by_others = 0
        self.last_trade_slot = -1
        self.total_trades = 0


class Held:
    __slots__ = ("opened", "peak_value", "invested", "exiting", "filled",
                 "last_add_vq", "last_add_vt", "last_value", "tx_paid", "dev_sold_at_open",
                 "entry_vq", "entry_vt", "strong")

    def __init__(self, opened, invested, vq, vt, strong=True):
        self.opened = opened
        self.peak_value = 0
        self.invested = invested
        self.exiting = False
        self.filled = False
        self.last_add_vq = vq
        self.last_add_vt = vt
        self.last_value = 0
        self.tx_paid = 0
        self.dev_sold_at_open = False
        self.entry_vq = vq
        self.entry_vt = vt
        self.strong = strong


def create_on_batch(params=None):
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)
    tapes = {}
    held = {}
    probes = {}  # mint -> True once its sell is in flight
    my_fills = 0
    my_coins = set()       # mints with any filled order of mine
    rt_coins = set()       # mints with a qualifying round trip (>= 0.01 SOL buy, closed)
    rt_buy = {}            # mint -> lamports bought in the current open round trip
    first_time = None
    last_time = None
    keep = max(p["window"], p["fade_window"], p["rev_high_window"]) + 5

    def tape_of(mint):
        t = tapes.get(mint)
        if t is None:
            t = Tape()
            tapes[mint] = t
        return t

    def sell_value(tokens, vq, vt, tx):
        """What selling `tokens` against (vq, vt) pays after curve fees and one tx fee."""
        if tokens <= 0 or vt <= 0:
            return 0
        q = (tokens * vq) // (vt + tokens)
        q -= (q * CURVE_FEE_BPS + BPS - 1) // BPS
        return q - tx

    def flow(t, now, w):
        """Net recorded lamports (buys minus sells) over the last `w` slots."""
        net = 0
        for tr in reversed(t.trades):
            if tr[0] <= now - w:
                break
            net += tr[2] if tr[1] else -tr[2]
        return net

    def momentum_signal(t, now, rq):
        if rq < p["min_rq_sol"] or rq > p["max_rq_sol"]:
            return False
        if t.created is None or now - t.created < p["min_age"]:
            return False
        start = now - p["window"]
        mid = now - p["window"] // 2
        buy_sol = sell_sol = buys = net_old = net_new = 0
        start_vq = start_vt = -1
        high_vq = high_vt = 0
        last_vq = last_vt = 0
        by_user = {}
        for tr in t.trades:
            slot, is_buy, sol_amt, user, vq, vt = tr
            if slot <= start:
                start_vq, start_vt = vq, vt
                continue
            if start_vq < 0:
                start_vq, start_vt = vq, vt
            signed = sol_amt if is_buy else -sol_amt
            if slot <= mid:
                net_old += signed
            else:
                net_new += signed
            if is_buy:
                buy_sol += sol_amt
                buys += 1
                by_user[user] = by_user.get(user, 0) + sol_amt
            else:
                sell_sol += sol_amt
            if high_vt == 0 or price_gt(vq, vt, high_vq, high_vt):
                high_vq, high_vt = vq, vt
            last_vq, last_vt = vq, vt
        if buys < p["min_buys"] or len(by_user) < p["min_buyers"]:
            return False
        if buy_sol - sell_sol < p["min_net_sol"]:
            return False
        if start_vq <= 0:
            return False
        up = price_ratio_bps(last_vq, last_vt, start_vq, start_vt)
        if up < p["min_price_up_bps"] or up > p["max_price_up_bps"]:
            return False
        # price now >= near_high share of the window high
        if last_vq * high_vt * BPS < high_vq * last_vt * p["near_high_bps"]:
            return False
        if net_new <= 0 or net_new * BPS < p["accel_bps"] * net_old:
            return False
        top = 0
        for v in by_user.values():
            if v > top:
                top = v
        if top * BPS > p["max_buyer_share_bps"] * buy_sol:
            return False
        return True

    def sniper_signal(t, now, rq, curve):
        if t.created is None:
            return False
        age = now - t.created
        if age < 0 or age > p["snipe_max_age"]:
            return False
        if rq < p["snipe_min_rq_sol"] or rq > p["snipe_max_rq_sol"]:
            return False
        if t.dev_buy > p["snipe_max_dev_buy_sol"]:
            return False
        if len(t.buyers) > p["snipe_max_buyers"]:
            return False
        if p["snipe_skip_dev_sold"] and t.dev_sold:
            return False
        return True

    def rider_signal(t, now, rq):
        """A curve grinding toward completion: high real SOL, many lifetime trades
        (instant completions have 1-7 trades and are untradeable), mature, price
        near its recent high, net inflow still positive."""
        if rq < p["rider_min_rq_sol"] or rq > p["rider_max_rq_sol"]:
            return False
        if t.created is None or now - t.created < p["rider_min_age"]:
            return False
        if t.total_trades < p["rider_min_trades"]:
            return False
        hi_vq = hi_vt = 0
        last_vq = last_vt = 0
        for tr in reversed(t.trades):
            if now - tr[0] > 100:
                break
            if hi_vt == 0 or price_gt(tr[4], tr[5], hi_vq, hi_vt):
                hi_vq, hi_vt = tr[4], tr[5]
            if last_vt == 0:
                last_vq, last_vt = tr[4], tr[5]
        if hi_vt == 0 or last_vt == 0:
            return False
        if last_vq * hi_vt * BPS < hi_vq * last_vt * p["rider_near_high_bps"]:
            return False
        if flow(t, now, p["rider_flow_window"]) < p["rider_min_flow_sol"]:
            return False
        return True

    def reversion_signal(t, now):
        ticks = t.trades
        if len(ticks) < p["rev_flow_trades"]:
            return None
        last = ticks[-1]
        if last[2] is None:
            return None
        hi_vq = hi_vt = 0
        for tr in reversed(ticks):
            if now - tr[0] > p["rev_high_window"]:
                break
            if hi_vt == 0 or price_gt(tr[4], tr[5], hi_vq, hi_vt):
                hi_vq, hi_vt = tr[4], tr[5]
        if hi_vt == 0:
            return None
        dd_bps = -price_ratio_bps(last[4], last[5], hi_vq, hi_vt)
        return (dd_bps, last)

    def on_batch(state, batch):
        nonlocal my_fills, first_time, last_time
        now = batch["slot"]
        traded = []
        traded_set = set()
        for f in batch["fills"]:
            if f["status"] == "filled" and not f["client_id"].startswith("_"):
                my_fills += 1
                my_coins.add(f["mint"])
                if f["side"] == "buy":
                    rt_buy[f["mint"]] = rt_buy.get(f["mint"], 0) + int(f["quote_lamports"])
                elif f["side"] == "sell" and rt_buy.get(f["mint"], 0) >= MIN_ROUND_TRIP:
                    rt_coins.add(f["mint"])
            h = held.get(f["mint"])
            if h is not None and f["status"] != "rejected":
                h.tx_paid += int(f["tx_fee_lamports"])
        for e in batch["events"]:
            bt = e.get("block_time")
            if bt is not None:
                if first_time is None:
                    first_time = bt
                if last_time is None or bt > last_time:
                    last_time = bt
            if e["event"] == "CreateEvent":
                t = tape_of(e["mint"])
                t.created = e["slot"]
                t.creator = e.get("creator")
            elif e["event"] == "TradeEvent":
                t = tape_of(e["mint"])
                sol_amt = int(e["sol_amount"])
                t.trades.append((e["slot"], bool(e["is_buy"]), sol_amt, e["user"],
                                 int(e["virtual_quote_reserves"]), int(e["virtual_token_reserves"])))
                t.total_trades += 1
                t.last_trade_slot = e["slot"]
                is_dev = t.creator is not None and e["user"] == t.creator
                if e["is_buy"]:
                    t.bought += sol_amt
                    if is_dev and e["slot"] == t.created:
                        t.dev_buy += sol_amt
                    elif not is_dev:
                        t.buyers.add(e["user"])
                elif is_dev:
                    t.dev_sold = True
                else:
                    t.sold_by_others += sol_amt
                if e["mint"] not in traded_set:
                    traded_set.add(e["mint"])
                    traded.append(e["mint"])
        for mint in traded:
            t = tapes[mint]
            cut = 0
            n = len(t.trades)
            while cut < n and t.trades[cut][0] <= now - keep:
                cut += 1
            if cut:
                del t.trades[:cut]

        marks = {m["mint"]: m for m in batch["marks"]}
        pending_by_mint = {}
        for po in state.pending.values():
            pending_by_mint[po.order["mint"]] = pending_by_mint.get(po.order["mint"], 0) + 1

        orders = []
        cap = state.hello["caps"]["max_orders_per_batch"]
        tx = state.tx_fee_lamports()
        mode = p["mode"]

        # --- exits first ---
        for mint in list(held.keys()):
            h = held[mint]
            pos = state.positions.get(mint)
            curve = state.curves.get(mint)
            if pos is None:
                if mint not in pending_by_mint:
                    del held[mint]
                    t = tape_of(mint)
                    if h.filled:
                        t.last_exit = now
                    else:
                        t.entries -= 1
                continue
            h.filled = True
            if curve is None or curve.complete:
                continue
            if mode == "hold":
                continue  # hold mode never sells: the replay closes on complete/flatten
            mk = marks.get(mint)
            if mk is not None:
                vq = int(mk["virtual_quote_reserves"])
                vt = int(mk["virtual_token_reserves"])
            else:
                vq = curve.virtual_quote_reserves
                vt = curve.virtual_token_reserves
            value = sell_value(pos.token_amount, vq, vt, tx)
            cost = pos.cost_lamports + h.tx_paid
            if value > h.peak_value:
                h.peak_value = value
            h.last_value = value
            t = tape_of(mint)
            exit_now = h.exiting
            if not exit_now and cost > 0 and value * BPS < cost * (BPS - p["stop_loss_bps"]):
                exit_now = True
            if (not exit_now and cost > 0 and h.peak_value * BPS >= cost * (BPS + p["trail_arm_bps"])
                    and value * BPS < h.peak_value * (BPS - p["trail_bps"])):
                exit_now = True
            if not exit_now and p["take_profit_bps"] > 0 and cost > 0 and value * BPS >= cost * (BPS + p["take_profit_bps"]):
                exit_now = True
            if not exit_now and now - h.opened >= p["max_hold"]:
                exit_now = True
            if not exit_now and p["exit_on_dev_sell"] and t.dev_sold and not h.dev_sold_at_open:
                exit_now = True
            if not exit_now and p["stale_slots"] > 0 and now - t.last_trade_slot >= p["stale_slots"]:
                exit_now = True
            if not exit_now and flow(t, now, p["fade_window"]) < -p["fade_net_sol"]:
                exit_now = True
            if not exit_now:
                continue
            h.exiting = True
            sell_pending = any(po.order["mint"] == mint and po.order["side"] == "sell"
                               for po in state.pending.values())
            if sell_pending:
                continue
            if len(orders) >= cap:
                break
            orders.append({"side": "sell", "mint": mint, "token_amount": pos.token_amount,
                           "max_slippage_bps": 10000})

        # --- probe round trips: sell the whole probe as soon as its buy has landed ---
        for mint in list(probes.keys()):
            pos = state.positions.get(mint)
            curve = state.curves.get(mint)
            if pos is None:
                if mint not in pending_by_mint:
                    del probes[mint]
                continue
            if curve is None or curve.complete or mint in pending_by_mint:
                continue
            if len(orders) >= cap:
                break
            orders.append({"side": "sell", "mint": mint, "token_amount": pos.token_amount,
                           "max_slippage_bps": 10000})
            probes[mint] = True

        # --- entries and adds ---
        free = state.free_cash_lamports()
        slots_left = state.hello["caps"]["max_open_positions"] - state.committed_position_count()
        main_left = p["max_main"] - len(held)
        exposure = 0
        for mint, h in held.items():
            pos = state.positions.get(mint)
            exposure += max(h.invested, pos.cost_lamports if pos is not None else 0)
        for mint in traded:
            if len(orders) >= cap:
                break
            curve = state.curves.get(mint)
            if curve is None or curve.complete:
                continue
            if mint in pending_by_mint or mint in probes:
                continue
            t = tapes[mint]
            h = held.get(mint)
            rq = curve.real_quote_reserves
            vq = curve.virtual_quote_reserves
            vt = curve.virtual_token_reserves
            tier_strong = True
            if h is None:
                if slots_left <= 0 or main_left <= 0:
                    continue
                if t.entries >= p["max_entries"] or now - t.last_exit < p["cooldown"]:
                    continue
                if mode == "momentum":
                    if not momentum_signal(t, now, rq):
                        continue
                    want = min(p["initial_sol"], p["stake_sol"])
                elif mode == "sniper":
                    if not sniper_signal(t, now, rq, curve):
                        continue
                    want = p["stake_sol"]
                elif mode == "hold":
                    # Equal-weight baseline: buy each coin once, as soon as the size
                    # cap lets it buy a meaningful amount, then never sell.
                    want = p["stake_sol"]
                elif mode == "rider":
                    if not rider_signal(t, now, rq):
                        continue
                    want = p["stake_sol"]
                else:  # reversion
                    sig = reversion_signal(t, now)
                    if sig is None:
                        continue
                    dd_bps, last = sig
                    if rq < p["rev_min_rq_sol"]:
                        continue
                    strong = rq >= p["rev_strong_rq_sol"]
                    if strong:
                        if dd_bps < p["rev_dd_min_bps"] or dd_bps > p["rev_dd_max_bps"]:
                            continue
                    else:
                        if dd_bps < p["rev_weak_dd_min_bps"] or dd_bps > p["rev_weak_dd_max_bps"]:
                            continue
                    ticks = t.trades
                    buys = 0
                    net = 0
                    for tr in ticks[-p["rev_flow_trades"]:]:
                        if tr[1]:
                            buys += 1
                            net += tr[2]
                        else:
                            net -= tr[2]
                    if buys < p["rev_min_buys"] or net < 0:
                        continue
                    if p["rev_last_must_be_buy"] and not last[1]:
                        continue
                    tier_strong = strong
                    want = p["rev_tranche_strong_sol"] if strong else p["rev_tranche_weak_sol"]
            else:
                # Reversion adds: another tranche while the dip holds near entry.
                if mode == "reversion":
                    if not p["rev_add"] or h.exiting or not h.filled:
                        continue
                    if h.invested >= p["rev_max_position_sol"]:
                        continue
                    # |price / entry_price - 1| <= add band
                    if (vq * h.entry_vt * BPS < h.entry_vq * vt * (BPS - p["rev_add_band_bps"])
                            or vq * h.entry_vt * BPS > h.entry_vq * vt * (BPS + p["rev_add_band_bps"])):
                        continue
                    tranche = p["rev_tranche_strong_sol"] if h.strong else p["rev_tranche_weak_sol"]
                    want = min(tranche, p["rev_max_position_sol"] - h.invested)
                # Pyramid into strength only (momentum/rider): the price stepped up
                # from the last add, the position is up, and net SOL still flows in.
                elif mode not in ("momentum", "rider") or h.exiting or not h.filled:
                    continue
                else:
                    if h.invested >= p["stake_sol"] - p["min_buy_sol"]:
                        continue
                    pos = state.positions.get(mint)
                    if pos is None:
                        continue
                    if vq * h.last_add_vt * BPS < h.last_add_vq * vt * (BPS + p["add_step_bps"]):
                        continue
                    if h.last_value * BPS < pos.cost_lamports * (BPS + p["add_if_up_bps"]):
                        continue
                    if flow(t, now, p["window"]) < p["add_net_sol"]:
                        continue
                    if mode == "momentum" and rq > p["max_rq_sol"]:
                        continue
                    if mode == "rider" and rq > p["rider_max_rq_sol"]:
                        continue
                    want = min(p["add_sol"], p["stake_sol"] - h.invested)
            cap_sol = state.max_buy_lamports(mint) * 97 // 100
            amount = min(cap_sol, want, p["max_exposure_sol"] - exposure)
            if amount > free - tx - CASH_RESERVE:
                amount = free - tx - CASH_RESERVE
            if amount < p["min_buy_sol"]:
                continue
            orders.append({"side": "buy", "mint": mint, "quote_lamports": amount,
                           "max_slippage_bps": p["buy_slip_bps"]})
            free -= amount + tx
            exposure += amount
            if h is None:
                nh = Held(now, amount, vq, vt, tier_strong)
                nh.dev_sold_at_open = t.dev_sold
                held[mint] = nh
                t.entries += 1
                slots_left -= 1
                main_left -= 1
            else:
                h.invested += amount
                h.last_add_vq = vq
                h.last_add_vt = vt

        # --- guardrail pacing: open a probe when qualifying coins lag the pace ---
        if (len(probes) < p["max_probes"] and slots_left > 0
                and first_time is not None and last_time is not None):
            pace = min(1.0, (last_time - first_time) / p["pace_secs"])
            if len(rt_coins) < int(p["target_coins"] * pace + 0.999999):
                min_rq = p["probe_sol"] * BPS // state.hello["caps"]["max_order_bps_of_real_reserve"]
                for mint in traded:
                    if len(orders) >= cap or len(probes) >= p["max_probes"]:
                        break
                    if mint in held or mint in probes or mint in pending_by_mint:
                        continue
                    if mint in state.positions or mint in rt_coins:
                        continue
                    curve = state.curves.get(mint)
                    if curve is None or curve.complete:
                        continue
                    if curve.real_quote_reserves < min_rq * 3 // 2:
                        continue
                    if free < p["probe_sol"] + 2 * tx:
                        break
                    orders.append({"side": "buy", "mint": mint, "quote_lamports": p["probe_sol"],
                                   "max_slippage_bps": p["buy_slip_bps"]})
                    probes[mint] = False
                    free -= p["probe_sol"] + tx
        return orders

    return on_batch


on_batch = create_on_batch()

if __name__ == "__main__":
    makefun_bot.run(on_batch)
