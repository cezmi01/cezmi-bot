"""Bundle execution logic."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount

from .config import BotConfig
from .logger import get_logger

LOGGER = get_logger()


@dataclass(slots=True)
class BundleTx:
    raw_tx: str
    can_revert: bool = False


class FlashbotsExecutor:
    """Minimal Flashbots relay integration."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        signer_key = config.bundle_signer_key or config.private_key
        self._bundle_signer: LocalAccount = Account.from_key(signer_key)
        self._http = httpx.AsyncClient(base_url=config.flashbots_relay, timeout=10)

    async def submit(self, txs: list[BundleTx], target_block: int) -> dict:
        signed = [tx.raw_tx for tx in txs]
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time()),
            "method": "eth_sendBundle",
            "params": [
                {
                    "txs": signed,
                    "blockNumber": hex(target_block),
                    "revertingTxHashes": [tx.raw_tx for tx in txs if tx.can_revert],
                }
            ],
        }
        headers = {"X-Flashbots-Signature": f"{self._bundle_signer.address}:{self._bundle_signer.key.hex()}"}
        response = await self._http.post("/", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        LOGGER.info("Bundle submitted: %s", data)
        return data
