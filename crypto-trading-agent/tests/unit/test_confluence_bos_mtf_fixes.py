"""
Focused unit tests for the Phase-2 confluence correctness fixes:

(a) ICT liquidity-sweep keys are aligned to the detector's real vocabulary
    ('asian_low_sweep', 'asian_high_sweep', 'previous_day_low_sweep',
    'swing_high_sweep') so ICT sweeps actually contribute confluence.
(b) BOS/CHoCH are detected across the whole series (SMC detector) and the
    confluence scorer reads the detector's native 'bullish_bos'/'bearish_bos'
    vocabulary.
(c) MTF price-trend slope thresholds are normalized by mean(close) so low-priced
    alts are not always read as 'neutral'.
"""
import numpy as np
import pandas as pd
import pytest

from src.strategy.confluence_scorer import ConfluenceScorer
from src.analysis.mtf_analyzer import MultiTimeframeAnalyzer
from src.analysis.smc_detector import SMCDetector


# ---------------------------------------------------------------------------
# (a) ICT liquidity-sweep key alignment
# ---------------------------------------------------------------------------
def test_ict_low_sweep_contributes_long_confluence():
    scorer = ConfluenceScorer()
    ict = {'liquidity_sweeps': [{'type': 'asian_low_sweep', 'reversed': True,
                                 'timeframe': '15m'}]}
    confs = scorer._score_ict(ict, 'LONG')
    assert any(c.factor == 'Liquidity Sweep' for c in confs), \
        "asian_low_sweep should support a LONG"

    # Same low sweep must NOT support a SHORT.
    assert not scorer._score_ict(ict, 'SHORT')


def test_ict_high_sweep_contributes_short_confluence():
    scorer = ConfluenceScorer()
    ict = {'liquidity_sweeps': [{'type': 'swing_high_sweep', 'reversed': True,
                                 'timeframe': '1h'}]}
    confs = scorer._score_ict(ict, 'SHORT')
    assert any(c.factor == 'Liquidity Sweep' for c in confs), \
        "swing_high_sweep should support a SHORT"
    assert not scorer._score_ict(ict, 'LONG')


def test_ict_previous_day_low_sweep_long():
    scorer = ConfluenceScorer()
    ict = {'liquidity_sweeps': [{'type': 'previous_day_low_sweep', 'reversed': True}]}
    assert scorer._score_ict(ict, 'LONG')


# ---------------------------------------------------------------------------
# (b) BOS/CHoCH scoring against the detector's native vocabulary
# ---------------------------------------------------------------------------
def test_scorer_reads_native_bos_vocabulary():
    scorer = ConfluenceScorer()
    smc = {
        'break_of_structure': {
            'bos': [{'type': 'bullish_bos', 'level': 100.0, 'timeframe': '1h'}],
            'choch': [],
            'current_trend': 'bullish',
        }
    }
    confs = scorer._score_smc(smc, 'LONG')
    assert any('BOS' in c.factor for c in confs), \
        "Native 'bullish_bos' must produce a BOS confluence for LONG"
    # A bullish BOS must not count for a SHORT.
    assert not any('BOS' in c.factor for c in scorer._score_smc(smc, 'SHORT'))


def test_scorer_reads_native_choch_vocabulary():
    scorer = ConfluenceScorer()
    smc = {
        'break_of_structure': {
            'bos': [],
            'choch': [{'type': 'bearish_choch', 'level': 90.0, 'timeframe': '1h'}],
            'current_trend': 'bearish',
        }
    }
    confs = scorer._score_smc(smc, 'SHORT')
    assert any('CHoCH' in c.factor for c in confs)


def test_legacy_bos_dict_still_supported():
    scorer = ConfluenceScorer()
    smc = {'break_of_structure': {'detected': True, 'direction': 'bullish',
                                  'timeframe': '1h'}}
    assert any('BOS' in c.factor for c in scorer._score_smc(smc, 'LONG'))


# ---------------------------------------------------------------------------
# (b) Series-wide BOS/CHoCH detection in the SMC detector
# ---------------------------------------------------------------------------
def _make_df(closes):
    n = len(closes)
    idx = pd.date_range('2024-01-01', periods=n, freq='h')
    closes = np.asarray(closes, dtype=float)
    # Build OHLC consistent with the close path.
    high = closes + 0.001 * closes
    low = closes - 0.001 * closes
    return pd.DataFrame(
        {'open': closes, 'high': high, 'low': low, 'close': closes,
         'volume': np.full(n, 1000.0)},
        index=idx,
    )


def test_series_bos_detected_not_only_last_bar():
    # Up-down-up shape produces swing points and at least one structural break
    # that occurs *before* the final bar.
    seg_up = list(np.linspace(100, 130, 25))
    seg_dn = list(np.linspace(130, 95, 25))
    seg_up2 = list(np.linspace(95, 140, 25))
    df = _make_df(seg_up + seg_dn + seg_up2)

    det = SMCDetector()
    result = det.detect_break_of_structure(df, swing_period=5)

    breaks = result['bos'] + result['choch']
    assert breaks, "Expected at least one structure break across the series"
    last_ts = str(df.index[-1])
    # Prove detection is genuinely series-wide, not just the final bar.
    assert any(b['timestamp'] != last_ts for b in breaks), \
        "Structure breaks should be detected on bars other than the last one"


# ---------------------------------------------------------------------------
# (c) MTF slope normalization for low-priced alts
# ---------------------------------------------------------------------------
def test_mtf_slope_normalized_for_low_priced_alt():
    analyzer = MultiTimeframeAnalyzer()

    # Low-priced alt rising ~1% per bar: raw slope is tiny (well under the old
    # absolute threshold of 10) but is clearly a strong uptrend after norming.
    closes = np.array([0.05 * (1.01 ** i) for i in range(40)])
    df = _make_df(closes)
    assert analyzer._get_price_trend(df) == 'bullish'

    # Falling low-priced alt -> bearish.
    closes_dn = np.array([0.05 * (0.99 ** i) for i in range(40)])
    df_dn = _make_df(closes_dn)
    assert analyzer._get_price_trend(df_dn) == 'bearish'


def test_mtf_slope_flat_is_neutral():
    analyzer = MultiTimeframeAnalyzer()
    df = _make_df(np.full(40, 0.05))
    assert analyzer._get_price_trend(df) == 'neutral'


def test_mtf_slope_still_works_for_high_priced_asset():
    analyzer = MultiTimeframeAnalyzer()
    closes = np.linspace(30000, 33000, 40)  # steady BTC-style uptrend
    df = _make_df(closes)
    assert analyzer._get_price_trend(df) == 'bullish'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
