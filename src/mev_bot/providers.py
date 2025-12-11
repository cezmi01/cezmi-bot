"""RPC and mempool provider helpers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from web3.providers.websocket import WebSocketProviderV2

from .config import BotConfig
from .logger import get_logger

LOGGER = get_logger()


class RPCProvider:
    """Wrapper around AsyncWeb3 to share http session."""

    def __init__(self, config: BotConfig) -> None:
        self._provider = AsyncHTTPProvider(config.rpc_url)
        self.web3 = AsyncWeb3(self._provider)

    async def latest_block(self) -> int:
        return await self.web3.eth.block_number


class MempoolStreamer:
    """Streams pending tx hashes from websocket endpoint."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._ws_url = config.require_ws_url()
        self._provider = WebSocketProviderV2(self._ws_url)
        self.web3 = AsyncWeb3(self._provider)

    @asynccontextmanager
    async def _subscription(self) -> AsyncIterator[Callable[[], Awaitable[None]]]:
        subscription = await self.web3.eth.subscribe("newPendingTransactions")
        try:
            yield subscription
        finally:
            await self.web3.eth.unsubscribe(subscription)

    async def stream(self) -> AsyncIterator[str]:
        """Yield pending tx hashes until cancelled."""

        retry_pause = 5
        while True:
            try:
                async with self._subscription() as subscription:
                    async for tx_hash in subscription:
                        yield tx_hash
            except Exception as exc:  # pragma: no cover - relies on network
                LOGGER.warning("Mempool stream error: %s", exc)
                await asyncio.sleep(retry_pause)
                retry_pause = min(retry_pause * 2, 60)
            else:
                retry_pause = 5
