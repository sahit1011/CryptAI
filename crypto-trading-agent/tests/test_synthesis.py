"""Per-user synthesis: choosing among shared candidates, never inventing a trade.

The safety line this pins: the model SELECTS and EXPLAINS. Price levels come from
deterministic analysis of real candles, because a hallucinated stop is indistinguishable
from a correct one until it fills. Every failure mode degrades to the deterministic pick
rather than costing the user a scan cycle.
"""
import pytest

from src.core.synthesis import BANNED, build_messages, build_synthesizer, parse_choice

CANDIDATES = [
    {"symbol": "BTCUSDT", "direction": "LONG", "entry_price": 64000.0, "stop_loss": 62000.0,
     "take_profit_levels": [{"price": 68000.0}], "strategy_type": "SWING",
     "confidence_score": 0.62},
    {"symbol": "ETHUSDT", "direction": "SHORT", "entry_price": 2500.0, "stop_loss": 2600.0,
     "take_profit_levels": [{"price": 2300.0}], "strategy_type": "SCALP",
     "confidence_score": 0.91},
]

PREFS = {
    "trading_capital": 10_000.0, "capital_currency": "USDT", "risk_appetite": "conservative",
    "max_risk_per_trade_pct": 1.0, "goal_horizon": "swing", "min_risk_reward": 2.0,
    "max_leverage": 3.0, "monthly_pnl_target_pct": 15.0, "goal_notes": "avoid funding spikes",
}

PULSES = {"BTCUSDT": {"regime": "trending_up", "tradability": 72, "vetoes": []}}


# --- the prompt ---------------------------------------------------------------

def test_prompt_carries_the_things_that_make_the_choice_personal():
    msgs = build_messages(CANDIDATES, PREFS, PULSES, [{"symbol": "SOLUSDT"}], "swing")
    user = msgs[1]["content"]
    for expected in ["conservative", "10000", "15.0", "avoid funding spikes", "SOLUSDT",
                     "trending_up", "BTCUSDT", "ETHUSDT"]:
        assert expected in user, f"prompt is missing {expected!r}"


def test_system_prompt_forbids_inventing_and_permits_declining():
    system = build_messages(CANDIDATES, PREFS, PULSES)[0]["content"]
    assert "Never invent" in system
    assert "choose none" in system.lower() or "declining" in system.lower()


def test_prompt_survives_missing_pulses_and_no_positions():
    msgs = build_messages(CANDIDATES, PREFS, {}, [], None)
    assert "no live condition scores available" in msgs[1]["content"]
    assert "already holding: none" in msgs[1]["content"]


# --- parsing the reply --------------------------------------------------------

def test_picks_the_named_candidate_and_keeps_the_thesis():
    idx, thesis = parse_choice('{"choice": 2, "thesis": "Price rejected the high. The stop sits above structure. A close back inside invalidates it."}', 2)
    assert idx == 1  # 1-based in the protocol, 0-based to the caller
    assert thesis.startswith("Price rejected")


def test_a_decline_is_a_valid_answer():
    assert parse_choice('{"choice": null, "thesis": ""}', 2) == (None, "")


def test_json_wrapped_in_prose_or_fences_is_still_read():
    idx, _ = parse_choice('Sure!\n```json\n{"choice": 1, "thesis": "a. b. c."}\n```', 2)
    assert idx == 0


@pytest.mark.parametrize("raw", [
    "", "not json at all", "{malformed", '{"choice": "two"}', '{"thesis": "no choice key"}',
    '[1, 2]',
])
def test_unusable_replies_degrade_to_no_pick(raw):
    assert parse_choice(raw, 2)[0] is None


@pytest.mark.parametrize("bad_index", [0, 3, -1, 99])
def test_an_out_of_range_choice_is_refused(bad_index):
    """A model naming candidate 7 of 2 must not index into the list."""
    assert parse_choice(f'{{"choice": {bad_index}, "thesis": "x"}}', 2)[0] is None


@pytest.mark.parametrize("thesis", [
    "This will hit 70000 easily.",
    "Price should reach the target.",
    "A guaranteed setup.",
    "I predict a bounce.",
    "This is certain to work.",
])
def test_a_forecasting_thesis_is_dropped_but_the_choice_survives(thesis):
    """The selection is still useful; the forecast is the thing that would mislead."""
    idx, out = parse_choice(f'{{"choice": 1, "thesis": "{thesis}"}}', 2)
    assert idx == 0, "the pick should survive a bad thesis"
    assert out == "", f"prediction language leaked: {thesis!r}"


def test_ordinary_past_tense_reasoning_is_kept():
    ok = "Price swept the low and reclaimed it. The stop sits under that wick, which suits your 1% risk. A close below invalidates the reclaim."
    assert not BANNED.search(ok)
    assert parse_choice(f'{{"choice": 1, "thesis": "{ok}"}}', 2)[1] == ok


# --- the synthesizer ----------------------------------------------------------

def _chat_returning(reply, usage=None, raises=False):
    async def chat(messages):
        if raises:
            raise RuntimeError("provider exploded")
        return reply, usage
    return chat


@pytest.mark.asyncio
async def test_chosen_setup_is_a_candidate_verbatim_plus_a_thesis():
    """The money-safety property: no invented prices, ever."""
    synth = build_synthesizer(
        _chat_returning('{"choice": 2, "thesis": "It did. It suits. It breaks."}',
                        usage={"input_tokens": 900, "output_tokens": 60}),
        model="test-model",
    )
    setup, usage, outcome = await synth(CANDIDATES, PREFS, PULSES)
    assert outcome == "chosen"
    assert setup["symbol"] == "ETHUSDT"
    # every price field identical to the source candidate
    for field in ("entry_price", "stop_loss", "take_profit_levels", "direction"):
        assert setup[field] == CANDIDATES[1][field]
    assert setup["thesis"] == "It did. It suits. It breaks."
    assert usage == {"input_tokens": 900, "output_tokens": 60}


@pytest.mark.asyncio
async def test_the_personal_choice_can_differ_from_raw_confidence():
    """The whole point: the conservative user is offered the 0.62 swing, not the 0.91
    scalp that would win a confidence sort."""
    synth = build_synthesizer(_chat_returning('{"choice": 1, "thesis": "a. b. c."}'))
    setup, _, _ = await synth(CANDIDATES, PREFS, PULSES)
    assert setup["symbol"] == "BTCUSDT"
    assert max(CANDIDATES, key=lambda c: c["confidence_score"])["symbol"] == "ETHUSDT"


@pytest.mark.asyncio
async def test_a_provider_failure_never_blocks_the_cycle():
    synth = build_synthesizer(_chat_returning("", raises=True))
    setup, usage, outcome = await synth(CANDIDATES, PREFS, PULSES)
    assert (setup, usage, outcome) == (None, None, "llm_error")


@pytest.mark.asyncio
async def test_a_decline_reports_itself_and_still_bills_the_tokens():
    """Declining costs real tokens; not billing them is how a cost cap leaks."""
    synth = build_synthesizer(
        _chat_returning('{"choice": null}', usage={"input_tokens": 800, "output_tokens": 5})
    )
    setup, usage, outcome = await synth(CANDIDATES, PREFS, PULSES)
    assert setup is None and outcome == "declined"
    assert usage == {"input_tokens": 800, "output_tokens": 5}


@pytest.mark.asyncio
async def test_no_candidates_short_circuits_before_paying_for_a_call():
    called = False

    async def chat(messages):
        nonlocal called
        called = True
        return "", None

    setup, usage, outcome = await build_synthesizer(chat)([], PREFS, PULSES)
    assert (setup, usage, outcome) == (None, None, "no_candidates")
    assert not called, "asked the model to choose among nothing"
