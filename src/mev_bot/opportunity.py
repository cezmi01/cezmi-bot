"""Opportunity discovery primitives."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, Sequence

from .dex_clients import PoolSnapshot, UniswapV2Client


@dataclass(slots=True)
class SwapLegTemplate:
    pool_address: str
    token_in: str
    token_out: str
    token_in_index: int = 0


@dataclass(slots=True)
class SwapLeg(SwapLegTemplate):
    snapshot: PoolSnapshot | None = None


@dataclass(slots=True)
class ArbitrageOpportunity:
    legs: Sequence[SwapLeg]
    amount_in: int
    expected_amount_out: int
    gas_cost_wei: int

    @property
    def profit(self) -> int:
        return self.expected_amount_out - self.amount_in - self.gas_cost_wei

    def profit_bps(self) -> float:
        if self.amount_in == 0:
            return 0.0
        return (self.profit / self.amount_in) * 10_000


class OpportunityDetector:
    """Runs simple triangular arbitrage scans."""

    def __init__(self, dex_client: UniswapV2Client, gas_price_wei: int) -> None:
        self._dex = dex_client
        self._gas_price = gas_price_wei
        self.rpc = dex_client.rpc

    def _simulate(self, amount_in: int, legs: Sequence[SwapLeg]) -> ArbitrageOpportunity | None:
        snapshots = [leg.snapshot for leg in legs]
        amount_out = self._dex.simulate_path(amount_in, snapshots)
        gas_cost = self._gas_price * 500_000  # rough default
        opportunity = ArbitrageOpportunity(legs=legs, amount_in=amount_in, expected_amount_out=amount_out, gas_cost_wei=gas_cost)
        if opportunity.profit <= 0:
            return None
        return opportunity

    async def detect(
        self,
        amount_in: int,
        candidate_paths: Iterable[Sequence[SwapLegTemplate]],
    ) -> list[ArbitrageOpportunity]:
        results: list[ArbitrageOpportunity] = []
        for path in candidate_paths:
            snapshot_tasks = [
                self._dex.fetch_snapshot(leg.pool_address, leg.token_in_index)
                for leg in path
            ]
            snapshots = await asyncio.gather(*snapshot_tasks)
            prepared_legs = [
                SwapLeg(
                    pool_address=leg.pool_address,
                    token_in=leg.token_in,
                    token_out=leg.token_out,
                    snapshot=snapshot,
                )
                for leg, snapshot in zip(path, snapshots, strict=False)
            ]
            maybe = self._simulate(amount_in, prepared_legs)
            if maybe:
                results.append(maybe)
        return results
