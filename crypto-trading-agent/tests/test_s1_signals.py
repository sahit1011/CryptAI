"""S1 confirmation primitives — the grammar of absorption-then-flip, pinned.

These functions are imported by BOTH the live paper engine and the offline backtest
lab, so a bug here poisons the experiment and the product at once. The tests build
tiny synthetic tapes where every threshold crossing is arranged by hand.
"""
import pytest

from src.strategy.s1_signals import (
    ConfirmedEntry,
    S1Params,
    confirm_entry,
    discount_band,
    latest_swing,
    participation_ok,
    taker_delta,
)

P = S1Params()


def bar(o=100.0, h=101.0, low=99.0, c=100.0, v=100.0, tb=50.0):
    return {"open": o, "high": h, "low": low, "close": c, "volume": v, "taker_buy_volume": tb}


def flat_tape(n, v=100.0):
    """n quiet bars: no aggression (delta 0), constant volume."""
    return [bar(v=v, tb=v / 2) for _ in range(n)]


# --------------------------------------------------------------------------- #
# taker delta
# --------------------------------------------------------------------------- #

def test_taker_delta_is_buys_minus_sells():
    assert taker_delta(bar(v=100, tb=70)) == pytest.approx(40.0)   # 70 buy / 30 sell
    assert taker_delta(bar(v=100, tb=20)) == pytest.approx(-60.0)  # 20 buy / 80 sell


def test_taker_delta_never_fabricates_on_missing_fields():
    assert taker_delta({"volume": 100.0}) == 0.0
    assert taker_delta({"taker_buy_volume": 50.0}) == 0.0
    assert taker_delta({"volume": None, "taker_buy_volume": 50.0}) == 0.0


# --------------------------------------------------------------------------- #
# swings and the band
# --------------------------------------------------------------------------- #

def test_latest_swing_finds_confirmed_fractals_only():
    tape = flat_tape(20)
    tape[8] = bar(h=105.0, low=99.0)   # swing high, confirmed by bars 9-11
    tape[14] = bar(h=101.0, low=95.0)  # swing low, confirmed by bars 15-17
    s = latest_swing(tape, left=3, right=3)
    assert s == {"high": 105.0, "high_index": 8, "low": 95.0, "low_index": 14}


def test_latest_swing_cannot_see_an_unconfirmed_extreme():
    """An extreme on the final bar is not knowable yet — returning it would be
    lookahead, and the lab's evidence would inherit the lie."""
    tape = flat_tape(20)
    tape[8] = bar(h=105.0, low=99.0)
    tape[14] = bar(h=101.0, low=95.0)
    tape.append(bar(h=200.0, low=10.0))  # both extremes, zero confirmation bars
    s = latest_swing(tape, left=3, right=3)
    assert s["high_index"] == 8 and s["low_index"] == 14


def test_latest_swing_needs_enough_bars():
    assert latest_swing(flat_tape(5), left=3, right=3) is None


def test_discount_band_geometry():
    lo, hi = 100.0, 200.0
    entry, invalid = discount_band(lo, hi, "long")
    assert entry == pytest.approx(200 - 70.5)   # 0.705 retracement
    assert invalid == pytest.approx(200 - 88.6)  # 0.886
    entry_s, invalid_s = discount_band(lo, hi, "short")
    assert entry_s == pytest.approx(100 + 70.5)
    assert invalid_s == pytest.approx(100 + 88.6)
    with pytest.raises(ValueError):
        discount_band(200.0, 100.0, "long")  # inverted impulse = fabricated level


# --------------------------------------------------------------------------- #
# participation
# --------------------------------------------------------------------------- #

def test_participation_passes_in_a_live_market_and_fails_in_a_dead_one():
    tape = flat_tape(60)
    assert participation_ok(tape, len(tape) - 1, P)  # steady volume clears a 1.0 floor
    dead = flat_tape(55) + [bar(v=10.0, tb=5.0) for _ in range(5)]
    assert not participation_ok(dead, len(dead) - 1, P)


def test_participation_fails_closed_on_thin_data():
    assert not participation_ok(flat_tape(6), 5, P)


# --------------------------------------------------------------------------- #
# the confirmation grammar
# --------------------------------------------------------------------------- #

def confirmation_tape():
    """60 quiet bars, then: touch → absorption (heavy selling, closes high) → flip
    (buyers dominant, close breaks the absorption high). Baseline mean volume is 100,
    so absorption needs delta ≤ -60 and the flip needs delta ≥ +30."""
    tape = flat_tape(60)
    touch = len(tape)
    tape.append(bar(o=100.3, h=100.4, low=99.5, c=100.0))                   # touch bar
    tape.append(bar(o=100.0, h=101.0, low=99.0, c=100.6, v=100, tb=20))     # absorption: δ=-60, closes top 20%
    tape.append(bar(o=100.6, h=101.5, low=100.2, c=101.2, v=100, tb=65))    # flip: δ=+30, close > 101.0
    return tape, touch


def test_confirm_entry_long_happy_path():
    tape, touch = confirmation_tape()
    e = confirm_entry(tape, touch, "long", P)
    assert isinstance(e, ConfirmedEntry)
    assert e.absorption_index == touch + 1
    assert e.entry_index == touch + 2
    assert e.entry_price == pytest.approx(101.2)     # the flip CLOSE — never the touch
    assert e.stop_price == pytest.approx(99.0 - 0.0005 * 101.2)  # behind the failed sellers


def test_no_absorption_means_no_trade():
    tape = flat_tape(60)
    touch = len(tape)
    tape.extend(flat_tape(35))  # quiet drift, nobody absorbs anything
    assert confirm_entry(tape, touch, "long", P) is None


def test_flip_without_participation_is_refused():
    tape, touch = confirmation_tape()
    # drain the flip bar's market: heavy RELATIVE delta but tiny absolute volume
    for i in range(touch, len(tape)):
        c = dict(tape[i])
        c["volume"] /= 20.0
        c["taker_buy_volume"] /= 20.0
        tape[i] = c
    assert confirm_entry(tape, touch, "long", P) is None


def test_close_beyond_invalidation_aborts():
    tape, touch = confirmation_tape()
    dead = dict(tape[touch + 1])
    dead["close"] = 98.0  # closes through the 0.886 edge before any flip
    dead["low"] = 97.9
    tape[touch + 1] = dead
    assert confirm_entry(tape, touch, "long", P, invalidation_price=98.5) is None


def test_confirm_entry_short_mirror():
    tape = flat_tape(60)
    touch = len(tape)
    tape.append(bar(o=99.7, h=100.5, low=99.6, c=100.0))                    # touch of the premium band
    tape.append(bar(o=100.0, h=101.0, low=99.0, c=99.4, v=100, tb=80))      # absorption: δ=+60, closes bottom 20%
    tape.append(bar(o=99.4, h=99.8, low=98.5, c=98.8, v=100, tb=35))        # flip: δ=-30, close < 99.0
    e = confirm_entry(tape, touch, "short", P)
    assert e is not None and e.direction == "short"
    assert e.entry_price == pytest.approx(98.8)
    assert e.stop_price == pytest.approx(101.0 + 0.0005 * 98.8)


def test_bad_direction_and_bad_index_return_none():
    tape, touch = confirmation_tape()
    assert confirm_entry(tape, touch, "sideways", P) is None
    assert confirm_entry(tape, 10_000, "long", P) is None
