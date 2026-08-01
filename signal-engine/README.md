# signal-engine

The shared signal plane. One process, always on, **no LLM and no `user_id`** — it computes
objective market facts identical for every tenant and publishes them to Redis. Its cost is
O(1) in user count, which is the whole reason the shared/per-user split exists
(`docs/MULTI_TENANCY.md`).

## Run it

```bash
# Redis must be reachable. If Homebrew's Cellar is not user-writable, build from source
# rather than sudo-chowning your Homebrew tree:
#   curl -fsSL -o redis.tar.gz https://download.redis.io/redis-stable.tar.gz
#   tar xzf redis.tar.gz && cd redis-stable && make -j8
#   ./src/redis-server --port 6379 --daemonize yes --save '' --appendonly no
# (The bundled RedisBloom/Search/JSON/TimeSeries modules fail to build on macOS and are
#  not used — redis-server and redis-cli come out fine.)

cargo build --release
SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT REDIS_URL=redis://localhost:6379 ./target/release/signal-engine
```

| Env | Default | Meaning |
|---|---|---|
| `SYMBOLS` | `BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT` | Comma-separated |
| `REDIS_URL` | `redis://localhost:6379` | |
| `TICK_MS` | `5000` | Scoring cadence |
| `WARMUP_BARS` | `250` | Minimum bars per timeframe before scoring |
| `RUST_LOG` | `info` | Tracing filter |

Startup backfills ~500 bars per symbol per timeframe over REST, then streams live. Without
that backfill the 4h timeframe would need weeks of uptime before the engine could score.

## What it publishes

`SET market:pulse:{SYMBOL}` (120s TTL) plus `PUBLISH market:pulse:updates:{SYMBOL}`.
Consumers need both: a session starting mid-stream reads the key, a running session
subscribes. The TTL matters — if the engine dies its keys **expire** rather than sitting
in Redis looking like current market state.

Read it from Python with `src.signals.PulseClient`, which enforces fail-closed staleness
and schema-version rejection at the boundary.

## Two invariants, enforced in code

1. **A pulse carries facts and scores, never a trade decision.** No entry, stop, target, or
   direction field — a test asserts none can appear. The moment the shared plane emits a
   trade, every user gets the same one and personalisation becomes a filter.
2. **A non-empty veto list forces `tradability` to 0**, in the constructor, so a caller
   cannot publish "vetoed but tradable".

## Layout

| Module | |
|---|---|
| `pulse` | The wire contract. The only interface to the rest of the system. |
| `indicators` | EMA, ATR (Wilder), Kaufman efficiency ratio, correlation. Pure, total. |
| `quant` | Yang-Zhang volatility, Lo-MacKinlay variance ratio, Hurst, robust z-scores. |
| `scoring` | Veto gates → weighted factors → regime. |
| `feature_store` | Bounded ring buffers per symbol/timeframe. |
| `ingest` | Binance websocket + REST bootstrap + funding/OI poller. |
| `publish` | Redis writer. |

`pulse`/`indicators`/`quant`/`scoring` are pure — no I/O, no runtime — so the math is
testable without a network. Only `ingest`/`publish`/`main` touch tokio.

## Verify

```bash
cargo test                                    # 100 tests
cargo clippy --all-targets -- -D warnings     # unwrap/panic/indexing are DENIED crate-wide
cargo fmt --check

# Differential test: numpy reimplements the same math and must agree.
cargo build --release --bin oracle
cd ../crypto-trading-agent && .venv/bin/pytest tests/test_pulse_differential.py
```

`unwrap`, `expect`, `panic`, and slice indexing are denied outside tests. A panic here
takes down the data source for every tenant simultaneously.

## Evaluation

`eval/FINDINGS.md` has the measured results and — more importantly — what is *not*
validated. Short version:

- The **tradability filter** validates at short horizon (IC +0.083 BTC / +0.096 XAUT at 4
  bars, surviving volatility normalisation). It decays to nothing by 24 bars.
- The **regime label does NOT validate as a direction call.** Out-of-sample on six
  held-out instruments: mean IC improvement −0.008, paired t −0.40, 3 of 6 improved.
  **`TrendingUp` does not mean "go long".** It is a description; direction is synthesised
  per-user.
- Weights in `Weights::default()` are an **uncalibrated prior**, not a finding.

```bash
cargo build --release --bin backtest
python eval/evaluate.py        # IC, IC decay, bucketed returns, deflated Sharpe
python eval/walkforward.py     # held-out instruments, parameter sweep, fold stability
```

Both use non-overlapping sampling and effective-n t-statistics. Earlier versions did
neither and reported Sharpes of −18 and t-statistics inflated ~5x.
