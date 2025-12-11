"""DEX adapters for price discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from web3.contract.async_contract import AsyncContract

from .providers import RPCProvider

UNISWAP_V2_PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "blockTimestampLast", "type": "uint32"},
        ],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }
]


@dataclass(slots=True)
class PoolSnapshot:
    """Simple struct capturing pool reserves."""

    reserve_in: int
    reserve_out: int
    fee_bps: int = 30

    def price(self) -> float:
        if self.reserve_in == 0 or self.reserve_out == 0:
            return 0.0
        return self.reserve_out / self.reserve_in


class UniswapV2Client:
    """Enough functionality to simulate constant product swaps."""

    def __init__(self, rpc: RPCProvider, fee_bps: int = 30) -> None:
        self._rpc = rpc
        self._fee_bps = fee_bps
        self.rpc = rpc

    def _contract(self, pool_address: str) -> AsyncContract:
        return self._rpc.web3.eth.contract(address=pool_address, abi=UNISWAP_V2_PAIR_ABI)

    async def fetch_snapshot(
        self, pool_address: str, token_in_index: int
    ) -> PoolSnapshot:
        contract = self._contract(pool_address)
        reserves = await contract.functions.getReserves().call()
        reserve0, reserve1, _ = reserves
        if token_in_index == 0:
            return PoolSnapshot(int(reserve0), int(reserve1), self._fee_bps)
        return PoolSnapshot(int(reserve1), int(reserve0), self._fee_bps)

    @staticmethod
    def _apply_fee(amount_in: int, fee_bps: int) -> int:
        return amount_in * (10_000 - fee_bps) // 10_000

    def estimate_amount_out(self, amount_in: int, snapshot: PoolSnapshot) -> int:
        amount_in_with_fee = self._apply_fee(amount_in, snapshot.fee_bps)
        numerator = amount_in_with_fee * snapshot.reserve_out
        denominator = snapshot.reserve_in + amount_in_with_fee
        return numerator // denominator

    def simulate_path(
        self, amount_in: int, snapshots: Sequence[PoolSnapshot]
    ) -> int:
        amount = amount_in
        for snapshot in snapshots:
            amount = self.estimate_amount_out(amount, snapshot)
            if amount <= 0:
                break
        return amount
