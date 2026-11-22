"""
Tests for numeric_core: the C++ still_core extension and its pure-Python port.

Every case from core_cpp/tests/*.cpp is ported here and run against each
backend that can be imported on this machine. When both are importable,
a randomized parity test checks they agree number-for-number.
"""

from __future__ import annotations

import importlib
import random

import pytest

from numeric_core import reference


def _compiled_or_none():
    try:
        return importlib.import_module("still_core")
    except ImportError:
        return None


_COMPILED = _compiled_or_none()
BACKENDS = [pytest.param(reference, id="python")]
if _COMPILED is not None:
    BACKENDS.append(pytest.param(_COMPILED, id="cpp"))

approx = pytest.approx


def _arousal(core, label="LOW", pause=0.0):
    return core.ArousalFeatures(pitch_mean=0.0, pitch_std=0.0, energy=0.0, zero_crossing_rate=0.0,
                                pause_ratio=pause, arousal_label=getattr(core.ArousalLabel, label))


def _emotion(core, **kw):
    values = dict(anger=0.0, disgust=0.0, fear=0.0, joy=0.0, neutral=0.0, sadness=0.0, surprise=0.0)
    values.update(kw)
    return core.EmotionScores(**values)


# --- test_turn_scoring.cpp --------------------------------------------------

@pytest.mark.parametrize("core", BACKENDS)
def test_turn_scoring_cases(core):
    scorer = core.TurnScorer()
    r = scorer.score(_arousal(core), _emotion(core))
    assert r.score == approx(0.0) and not r.flagged_high_pause

    r = scorer.score(_arousal(core, "HIGH", 1.0),
                     _emotion(core, anger=1.0, disgust=1.0, fear=1.0, sadness=1.0))
    assert r.score == approx(100.0) and r.flagged_high_pause

    assert not scorer.score(_arousal(core, pause=0.5), _emotion(core)).flagged_high_pause  # strictly >
    assert scorer.score(_arousal(core, "MODERATE"), _emotion(core)).score == approx(0.4 * 50.0)


# --- test_session_stats.cpp -------------------------------------------------

@pytest.mark.parametrize("core", BACKENDS)
def test_session_stats_cases(core):
    calc = core.SessionStatsCalculator
    s = calc.compute([50.0, 50.0, 50.0])
    assert (s.mean_score, s.max_score, s.min_score, s.volatility, s.within_session_trend) == approx(
        (50.0, 50.0, 50.0, 0.0, 0.0))

    s = calc.compute([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0])
    assert (s.mean_score, s.max_score, s.min_score, s.within_session_trend) == approx((50.0, 90.0, 10.0, 10.0))

    s = calc.compute([10.0, 90.0, 10.0, 90.0, 10.0, 90.0])
    assert s.within_session_trend == approx(0.0) and s.volatility > 30.0

    s = calc.compute([42.0])
    assert (s.mean_score, s.volatility, s.within_session_trend) == approx((42.0, 0.0, 0.0))

    s = calc.compute([10.0, 90.0])
    assert s.within_session_trend == approx(0.0) and s.volatility > 0.0

    s = calc.compute([])
    assert (s.mean_score, s.volatility) == approx((0.0, 0.0))


# --- test_trend_regression.cpp ----------------------------------------------

@pytest.mark.parametrize("core", BACKENDS)
def test_trend_regression_cases(core):
    tp = core.TrendPoint
    reg = core.TrendRegressor()
    for pts in ([tp(timestamp_days=0.0, mean_score=50.0)], []):
        r = reg.fit(pts)
        assert (r.slope, r.confidence) == approx((0.0, 0.0), abs=1e-4)

    linear = [tp(timestamp_days=float(d), mean_score=50.0 + d) for d in range(4)]
    assert core.TrendRegressor(half_life_days=100000.0).fit(linear).slope == approx(1.0, abs=1e-2)

    two = [tp(timestamp_days=0.0, mean_score=50.0), tp(timestamp_days=1.0, mean_score=40.0)]
    five = [tp(timestamp_days=float(d), mean_score=50.0 - 5 * d) for d in range(5)]
    r2, r5 = reg.fit(two), reg.fit(five)
    assert r2.confidence < r5.confidence < 1.0

    reversal = [tp(timestamp_days=float(d), mean_score=v) for d, v in enumerate([30.0, 32.0, 34.0, 36.0, 20.0])]
    assert core.TrendRegressor(half_life_days=1.0).fit(reversal).slope < 0.0


# --- test_risk_aggregation.cpp ----------------------------------------------

def _inputs(core, slope, conf, mean, vol, within, acute):
    return core.RiskInputs(trend_slope=slope, trend_confidence=conf, session_mean_score=mean,
                           session_volatility=vol, session_within_trend=within, acute_override=acute)


@pytest.mark.parametrize("core", BACKENDS)
def test_risk_aggregation_cases(core):
    agg = core.RiskAggregator()
    r = agg.aggregate(_inputs(core, 2.0, 0.9, 10.0, 1.0, 1.0, False))
    assert r.risk_score < 20.0 and r.contributing_features

    assert agg.aggregate(_inputs(core, -5.0, 0.9, 95.0, 25.0, -5.0, False)).risk_score > 70.0

    r = agg.aggregate(_inputs(core, 5.0, 0.9, 5.0, 0.0, 5.0, True))
    assert r.risk_score == approx(100.0)
    assert any(f.name == "acute_override" for f in r.contributing_features)

    assert agg.aggregate(_inputs(core, -10.0, 0.0, 0.0, 0.0, 0.0, False)).risk_score == approx(0.0)


@pytest.mark.parametrize("core", BACKENDS)
def test_risk_feature_names_and_order(core):
    names = [f.name for f in core.RiskAggregator().aggregate(_inputs(core, -1.0, 0.5, 40.0, 3.0, 0.0, True))
             .contributing_features]
    assert names == ["trend_slope", "session_mean_score", "recent_volatility", "acute_override"]


# --- C++ vs Python parity (only where the extension loads) ------------------

@pytest.mark.skipif(_COMPILED is None, reason="still_core C++ extension not importable here")
def test_cpp_and_python_agree_on_random_inputs():
    rng = random.Random(26094)
    cpp, py = _COMPILED, reference
    for _ in range(500):
        label = rng.choice(["LOW", "MODERATE", "HIGH"])
        pause = rng.random()
        emo = {k: rng.random() for k in ("anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise")}
        a = cpp.TurnScorer().score(_arousal(cpp, label, pause), _emotion(cpp, **emo))
        b = py.TurnScorer().score(_arousal(py, label, pause), _emotion(py, **emo))
        assert a.score == approx(b.score, abs=1e-9) and a.flagged_high_pause == b.flagged_high_pause

        scores = [rng.uniform(0, 100) for _ in range(rng.randint(0, 12))]
        sa, sb = cpp.SessionStatsCalculator.compute(scores), py.SessionStatsCalculator.compute(scores)
        for attr in ("mean_score", "max_score", "min_score", "volatility", "within_session_trend"):
            assert getattr(sa, attr) == approx(getattr(sb, attr), abs=1e-9)

        days = sorted(rng.uniform(0, 60) for _ in range(rng.randint(0, 10)))
        means = [rng.uniform(0, 100) for _ in days]
        ta = cpp.TrendRegressor().fit([cpp.TrendPoint(timestamp_days=d, mean_score=m) for d, m in zip(days, means)])
        tb = py.TrendRegressor().fit([py.TrendPoint(timestamp_days=d, mean_score=m) for d, m in zip(days, means)])
        assert (ta.slope, ta.confidence) == approx((tb.slope, tb.confidence), abs=1e-9)

        args = (rng.uniform(-3, 3), rng.random(), rng.uniform(0, 100), rng.uniform(0, 30),
                rng.uniform(-5, 5), rng.random() < 0.1)
        ra, rb = cpp.RiskAggregator().aggregate(_inputs(cpp, *args)), py.RiskAggregator().aggregate(_inputs(py, *args))
        assert ra.risk_score == approx(rb.risk_score, abs=1e-9)
        assert [(f.name, f.value, f.weight) for f in ra.contributing_features] == approx(
            [(f.name, f.value, f.weight) for f in rb.contributing_features])
