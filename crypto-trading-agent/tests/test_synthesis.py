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
    verdict, idx, thesis = parse_choice('{"choice": 2, "thesis": "Price rejected the high. The stop sits above structure. A close back inside invalidates it."}', 2)
    assert verdict == "picked"
    assert idx == 1  # 1-based in the protocol, 0-based to the caller
    assert thesis.startswith("Price rejected")


def test_a_decline_is_a_valid_answer():
    verdict, idx, _ = parse_choice('{"choice": null, "thesis": ""}', 2)
    assert (verdict, idx) == ("declined", None)


@pytest.mark.parametrize("raw,why", [
    ("Candidate 1 suits this trader: the pullback already happened.", "prose, no JSON"),
    ('{"choice": 1, "thesis": "it happened', "truncated mid-JSON by max_tokens"),
    ('{"thesis": "no choice key"}', "missing the choice key"),
    ('{"choice": "two"}', "non-numeric choice"),
    ('{"choice": 7}', "out of range"),
])
def test_an_unreadable_reply_is_never_reported_as_a_decline(raw, why):
    """The blocker this pins: a free instruct model answering in prose, or a reply cut off
    by max_tokens, was being shown to the user as 'none of these fit your rules' — a
    judgment their agent never made, on a metered cycle."""
    verdict, idx, _ = parse_choice(raw, 2)
    assert verdict == "unreadable", f"{why} was misread as a considered answer"
    assert idx is None


def test_json_wrapped_in_prose_or_fences_is_still_read():
    verdict, idx, _ = parse_choice('Sure!\n```json\n{"choice": 1, "thesis": "a. b. c."}\n```', 2)
    assert (verdict, idx) == ("picked", 0)


@pytest.mark.parametrize("raw", [
    "", "not json at all", "{malformed", '{"choice": "two"}', '{"thesis": "no choice key"}',
    '[1, 2]',
])
def test_unusable_replies_degrade_to_no_pick(raw):
    assert parse_choice(raw, 2)[0] == "unreadable"


@pytest.mark.parametrize("bad_index", [0, 3, -1, 99])
def test_an_out_of_range_choice_is_refused(bad_index):
    """A model naming candidate 7 of 2 must not index into the list."""
    assert parse_choice(f'{{"choice": {bad_index}, "thesis": "x"}}', 2)[0] == "unreadable"


@pytest.mark.parametrize("thesis", [
    "This will hit 70000 easily.",
    "Price should reach the target.",
    "A guaranteed setup.",
    "I predict a bounce.",
    "This is certain to work.",
])
def test_a_forecasting_thesis_is_dropped_but_the_choice_survives(thesis):
    """The selection is still useful; the forecast is the thing that would mislead."""
    verdict, idx, out = parse_choice(f'{{"choice": 1, "thesis": "{thesis}"}}', 2)
    assert (verdict, idx) == ("picked", 0), "the pick should survive a bad thesis"
    assert out == "", f"prediction language leaked: {thesis!r}"


def test_ordinary_past_tense_reasoning_is_kept():
    ok = "Price swept the low and reclaimed it. The stop sits under that wick, which suits your 1% risk. A close below invalidates the reclaim."
    assert not BANNED.search(ok)
    assert parse_choice(f'{{"choice": 1, "thesis": "{ok}"}}', 2)[2] == ok


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


# --- the OpenRouter rotation --------------------------------------------------

class _FakeCompletions:
    """Minimal stand-in for client.chat.completions with per-model behaviour."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.tried = []

    def create(self, model, messages, max_tokens, temperature):
        self.tried.append(model)
        outcome = self.behaviour.get(model, "ok")
        if outcome == "raise":
            raise RuntimeError(f"{model} is 429ing")
        body = "" if outcome == "empty" else '{"choice": 1, "thesis": "a. b. c."}'
        return type("R", (), {
            "choices": [type("C", (), {"message": type("M", (), {"content": body})()})()],
            "usage": {"input_tokens": 10, "output_tokens": 4},
        })()


def _client(behaviour):
    comp = _FakeCompletions(behaviour)
    client = type("Client", (), {"chat": type("Chat", (), {"completions": comp})()})()
    return client, comp


@pytest.mark.asyncio
async def test_rotation_falls_through_a_pulled_model():
    """A pinned free model that gets pulled is what made this engine silently produce
    nothing before — the rotation must walk past it."""
    from src.core.synthesis import build_openai_compatible_chat

    client, comp = _client({"dead:free": "raise", "alive:free": "ok"})
    chat = build_openai_compatible_chat(client, ["dead:free", "alive:free"])
    text, usage = await chat([{"role": "user", "content": "x"}])
    assert comp.tried == ["dead:free", "alive:free"]
    assert "choice" in text
    # Normalized to the names SessionBudget bills, and tagged with the model that
    # actually served — the fallback model, not the first one tried.
    assert usage["input_tokens"] == 10 and usage["output_tokens"] == 4
    assert usage["model"] == "alive:free"


@pytest.mark.asyncio
async def test_an_empty_body_counts_as_a_dead_slot():
    """Free slots answer 200 with an empty body; treating that as an answer yields a
    silent no-op instead of a fallback."""
    from src.core.synthesis import build_openai_compatible_chat

    client, comp = _client({"hollow:free": "empty", "alive:free": "ok"})
    chat = build_openai_compatible_chat(client, ["hollow:free", "alive:free"])
    text, _ = await chat([{"role": "user", "content": "x"}])
    assert comp.tried == ["hollow:free", "alive:free"]
    assert "choice" in text


@pytest.mark.asyncio
async def test_the_first_healthy_model_wins_and_the_rest_are_untouched():
    from src.core.synthesis import build_openai_compatible_chat

    client, comp = _client({})
    chat = build_openai_compatible_chat(client, ["a:free", "b:free", "c:free"])
    await chat([{"role": "user", "content": "x"}])
    assert comp.tried == ["a:free"], "paid for models it did not need"


@pytest.mark.asyncio
async def test_every_model_failing_raises_so_the_caller_falls_back():
    """The synthesizer catches this and uses the deterministic pick — but it must SEE
    a failure rather than a silent empty answer."""
    from src.core.synthesis import build_openai_compatible_chat

    client, _ = _client({"a:free": "raise", "b:free": "raise"})
    chat = build_openai_compatible_chat(client, ["a:free", "b:free"])
    with pytest.raises(Exception):
        await chat([{"role": "user", "content": "x"}])

    # …and the synthesizer turns that into the documented fallback, not a crash.
    setup, usage, outcome = await build_synthesizer(chat)(CANDIDATES, PREFS, PULSES)
    assert (setup, usage, outcome) == (None, None, "llm_error")


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


# --- the meter actually moves -------------------------------------------------
#
# The blocker these pin: usage was handed back in the provider's OWN shape
# (prompt_tokens/completion_tokens), while SessionBudget.record_response reads Anthropic
# names. Every lookup missed, so every synthesis call booked ZERO while the commit claimed
# the cost cap finally guarded a real number. The earlier tests passed a hand-written
# {"input_tokens": ...} dict — a shape production never produces — which is exactly why
# they proved threading and not billing.

class _OpenAIUsage:
    """The real OpenAI/OpenRouter CompletionUsage field names."""

    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


@pytest.mark.asyncio
async def test_openai_usage_is_translated_into_what_the_budget_bills():
    from src.core.synthesis import build_openai_compatible_chat

    comp = _FakeCompletions({})
    comp.create = lambda model, messages, max_tokens, temperature: type("R", (), {
        "choices": [type("C", (), {"message": type("M", (), {
            "content": '{"choice": 1, "thesis": "a. b. c."}'})()})()],
        "usage": _OpenAIUsage(1500, 400),
    })()
    client = type("Client", (), {"chat": type("Chat", (), {"completions": comp})()})()

    _, usage = await build_openai_compatible_chat(client, ["m:free"])([{"role": "u", "content": "x"}])
    assert usage["input_tokens"] == 1500, "prompt_tokens was not translated"
    assert usage["output_tokens"] == 400, "completion_tokens was not translated"


def test_the_budget_books_a_real_charge_from_that_shape():
    """End of the chain: a normalized usage dict must move llm_cost_micros off zero."""
    from src.core.session_budget import cost_micros

    charged = cost_micros("claude-sonnet-5", input_tokens=1500, output_tokens=400)
    assert charged > 0, "a priced model booked nothing"


def test_free_models_cost_nothing_instead_of_the_unknown_tier():
    """A :free model priced at the $10/$50 unknown fallback would end a session on the
    cost cap for spend that never happened — the cap firing hardest on the deployment
    paying least."""
    from src.core.session_budget import cost_micros, pricing_for

    free = pricing_for("nvidia/nemotron-3-super-120b-a12b:free")
    assert (free.input_per_mtok, free.output_per_mtok) == (0.0, 0.0)
    assert cost_micros("nvidia/nemotron-3-super-120b-a12b:free", 1_000_000, 500_000) == 0
    # A genuinely unknown paid model still gets the conservative fallback.
    assert cost_micros("some/unlisted-paid-model", 1_000_000, 0) > 0


@pytest.mark.parametrize("forecast", [
    "BTC will likely reach 70000 before the stop.",   # adverb defeated the first version
    "This should hit TP1 within the session.",         # 'should hit' was uncovered
    "Price is going to hit 70k.",
    "I expect a move to 70k.",                         # forecast verb, no target verb
    "The trend will continue higher.",
    "This will break out of the range.",
    "Highly likely to reach target 1.",
    "We anticipate a retest.",
])
def test_the_forecast_lint_is_not_defeated_by_an_adverb_or_a_synonym(forecast):
    """A review found every one of these sailing through the first regex, which required
    the future-tense word and the price verb to be adjacent."""
    assert BANNED.search(forecast), f"forecast leaked to the user: {forecast!r}"


@pytest.mark.parametrize("legitimate", [
    "Price swept the low and reclaimed it. The stop sits under that wick. A close below invalidates the reclaim.",
    "The range held twice. Entry sits at its lower edge, which suits your 1% risk. Losing that edge kills it.",
    "Volume expanded on the break and price retested it. This fits your swing horizon. A close back inside is the invalidation.",
    "Funding flipped negative while price held. That suits your conservative sizing. A reclaim of the high ends the thesis.",
])
def test_the_lint_does_not_eat_ordinary_past_tense_reasoning(legitimate):
    """A lint that blocks real theses is worse than none — it silently empties the card."""
    assert not BANNED.search(legitimate), f"false positive: {legitimate!r}"
