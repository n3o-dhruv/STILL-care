"""
numeric_core/reference.py

Pure-Python reference implementation of the `still_core` C++ extension
(core_cpp/). Same classes, constructor arguments, attribute names, defaults
and formulas, ported line for line from core_cpp/src/*.cpp, so callers
can't tell which one they got.

Why it exists: some machines can't load the compiled extension (no C++
toolchain, or Windows Application Control / Smart App Control blocking
unsigned DLLs). The pipeline then still runs, with identical results.

Keep in sync with core_cpp/: any formula change there must be mirrored
here. tests/test_numeric_core.py checks both against the same expectations
and, when the extension is importable, against each other.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Sequence


def _clamp0_100(v: float) -> float:
    return min(100.0, max(0.0, v))


# ---------------------------------------------------------------------------
# turn_scoring.{h,cpp}
# ---------------------------------------------------------------------------

class ArousalLabel(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2


_AROUSAL_BASE = (0.0, 50.0, 100.0)  # indexed by ArousalLabel value


@dataclass
class ArousalFeatures:
    pitch_mean: float = 0.0
    pitch_std: float = 0.0
    energy: float = 0.0
    zero_crossing_rate: float = 0.0
    pause_ratio: float = 0.0
    arousal_label: ArousalLabel = ArousalLabel.LOW


@dataclass
class EmotionScores:
    anger: float = 0.0
    disgust: float = 0.0
    fear: float = 0.0
    joy: float = 0.0
    neutral: float = 0.0
    sadness: float = 0.0
    surprise: float = 0.0


@dataclass(frozen=True)
class TurnScoreResult:
    score: float = 0.0
    flagged_high_pause: bool = False


class TurnScorer:
    def __init__(self, arousal_weight: float = 0.4, pause_weight: float = 0.2,
                 emotion_weight: float = 0.4, high_pause_threshold: float = 0.5) -> None:
        self._arousal_weight = arousal_weight
        self._pause_weight = pause_weight
        self._emotion_weight = emotion_weight
        self._high_pause_threshold = high_pause_threshold

    def score(self, arousal: ArousalFeatures, emotion: EmotionScores) -> TurnScoreResult:
        arousal_component = _AROUSAL_BASE[int(arousal.arousal_label)]
        pause_component = _clamp0_100(arousal.pause_ratio * 100.0)
        negative_mass = emotion.anger + emotion.disgust + emotion.fear + emotion.sadness
        emotion_component = _clamp0_100(negative_mass * 100.0)
        raw = (self._arousal_weight * arousal_component
               + self._pause_weight * pause_component
               + self._emotion_weight * emotion_component)
        return TurnScoreResult(_clamp0_100(raw), arousal.pause_ratio > self._high_pause_threshold)


# ---------------------------------------------------------------------------
# session_stats.{h,cpp}
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionStats:
    mean_score: float = 0.0
    max_score: float = 0.0
    min_score: float = 0.0
    volatility: float = 0.0
    within_session_trend: float = 0.0


class SessionStatsCalculator:
    @staticmethod
    def compute(scores: Sequence[float]) -> SessionStats:
        n = len(scores)
        if n == 0:
            return SessionStats()

        total = 0.0
        for s in scores:
            total += s
        mean = total / n

        volatility = 0.0
        if n > 1:
            sq_diff_sum = 0.0
            for s in scores:
                d = s - mean
                sq_diff_sum += d * d
            volatility = math.sqrt(sq_diff_sum / (n - 1))  # sample std dev

        within_session_trend = 0.0
        if n >= 3:
            third = n // 3
            first_third_mean = sum(scores[:third]) / third
            last_third_mean = sum(scores[n - third:]) / third
            first_mid_index = (third - 1.0) / 2.0
            last_mid_index = (n - third) + (third - 1.0) / 2.0
            index_distance = last_mid_index - first_mid_index
            within_session_trend = (
                (last_third_mean - first_third_mean) / index_distance if index_distance > 0.0 else 0.0
            )

        return SessionStats(mean, max(scores), min(scores), volatility, within_session_trend)


# ---------------------------------------------------------------------------
# trend_regression.{h,cpp}
# ---------------------------------------------------------------------------

@dataclass
class TrendPoint:
    timestamp_days: float = 0.0
    mean_score: float = 0.0


@dataclass(frozen=True)
class TrendResult:
    slope: float = 0.0
    confidence: float = 0.0


class TrendRegressor:
    def __init__(self, half_life_days: float = 14.0, confidence_growth_rate: float = 0.5) -> None:
        self._half_life_days = half_life_days
        self._confidence_growth_rate = confidence_growth_rate

    def fit(self, points: Sequence[TrendPoint]) -> TrendResult:
        n = len(points)
        if n < 2:
            return TrendResult()

        most_recent_t = points[-1].timestamp_days
        decay_lambda = math.log(2.0) / self._half_life_days

        sum_w = sum_wx = sum_wy = 0.0
        for p in points:
            w = math.exp(-decay_lambda * (most_recent_t - p.timestamp_days))
            sum_w += w
            sum_wx += w * p.timestamp_days
            sum_wy += w * p.mean_score
        x_bar = sum_wx / sum_w
        y_bar = sum_wy / sum_w

        sum_w_dx_dy = sum_w_dx2 = 0.0
        for p in points:
            w = math.exp(-decay_lambda * (most_recent_t - p.timestamp_days))
            dx = p.timestamp_days - x_bar
            dy = p.mean_score - y_bar
            sum_w_dx_dy += w * dx * dy
            sum_w_dx2 += w * dx * dx

        slope = sum_w_dx_dy / sum_w_dx2 if sum_w_dx2 > 1e-12 else 0.0
        confidence = 1.0 - math.exp(-self._confidence_growth_rate * (n - 1))
        return TrendResult(slope, confidence)


# ---------------------------------------------------------------------------
# risk_aggregation.{h,cpp}
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContributingFeature:
    name: str
    value: float = 0.0
    weight: float = 0.0


@dataclass
class RiskInputs:
    trend_slope: float = 0.0
    trend_confidence: float = 0.0
    session_mean_score: float = 0.0
    session_volatility: float = 0.0
    session_within_trend: float = 0.0
    acute_override: bool = False


@dataclass(frozen=True)
class RiskAssessment:
    risk_score: float = 0.0
    contributing_features: List[ContributingFeature] = field(default_factory=list)


class RiskAggregator:
    def __init__(self, trend_weight: float = 0.4, session_score_weight: float = 0.35,
                 volatility_weight: float = 0.25, volatility_scale: float = 4.0) -> None:
        self._trend_weight = trend_weight
        self._session_score_weight = session_score_weight
        self._volatility_weight = volatility_weight
        self._volatility_scale = volatility_scale

    def aggregate(self, inputs: RiskInputs) -> RiskAssessment:
        features: List[ContributingFeature] = []

        trend_component = _clamp0_100(-inputs.trend_slope * 100.0) * inputs.trend_confidence
        features.append(ContributingFeature("trend_slope", inputs.trend_slope,
                                            self._trend_weight * inputs.trend_confidence))

        session_component = _clamp0_100(inputs.session_mean_score)
        features.append(ContributingFeature("session_mean_score", inputs.session_mean_score,
                                            self._session_score_weight))

        volatility_component = _clamp0_100(inputs.session_volatility * self._volatility_scale)
        features.append(ContributingFeature("recent_volatility", inputs.session_volatility,
                                            self._volatility_weight))

        risk_score = _clamp0_100(self._trend_weight * trend_component
                                 + self._session_score_weight * session_component
                                 + self._volatility_weight * volatility_component)

        if inputs.acute_override:
            risk_score = 100.0
            features.append(ContributingFeature("acute_override", 1.0, 1.0))

        return RiskAssessment(risk_score, features)
