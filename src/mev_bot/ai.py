"""Simple AI-assisted scoring for opportunities."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
from joblib import load

from .opportunity import ArbitrageOpportunity


class OpportunityScorer:
    """Wrapper around a sklearn-like probability model."""

    def __init__(self, model_path: Path | str | None = None) -> None:
        self._model = None
        if model_path and Path(model_path).exists():
            self._model = load(model_path)

    def _features(self, opportunity: ArbitrageOpportunity) -> list[float]:
        legs = opportunity.legs
        avg_pool_price = np.mean([leg.snapshot.price() if leg.snapshot else 0 for leg in legs])
        return [
            float(opportunity.profit_bps()),
            float(len(legs)),
            avg_pool_price,
            float(opportunity.gas_cost_wei),
        ]

    def score(self, opportunity: ArbitrageOpportunity) -> float:
        features = np.array([self._features(opportunity)])
        if self._model is None:
            # Heuristic fallback: emphasize profit and penalize gas
            raw = opportunity.profit_bps() - (opportunity.gas_cost_wei / 1e16)
            return max(min(raw / 100, 1), 0)
        proba = self._model.predict_proba(features)
        return float(proba[0][1])

    def rank(self, opportunities: Iterable[ArbitrageOpportunity]) -> list[ArbitrageOpportunity]:
        return sorted(opportunities, key=self.score, reverse=True)
