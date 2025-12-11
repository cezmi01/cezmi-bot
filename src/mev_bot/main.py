"""Async entrypoint for the MEV bot."""

from __future__ import annotations

import asyncio
from typing import Iterable, Sequence

from .ai import OpportunityScorer
from .config import BotConfig
from .dex_clients import UniswapV2Client
from .executor import BundleTx, FlashbotsExecutor
from .logger import get_logger
from .opportunity import ArbitrageOpportunity, OpportunityDetector, SwapLegTemplate
from .providers import MempoolStreamer, RPCProvider

LOGGER = get_logger()


def build_candidate_paths(config: BotConfig) -> Iterable[Sequence[SwapLegTemplate]]:
    """Placeholder path builder; replace with real graph discovery."""

    for pair in config.target_pairs:
        yield (
            SwapLegTemplate(
                pool_address="0xPoolA",
                token_in=pair.base,
                token_out=pair.quote,
                token_in_index=0,
            ),
            SwapLegTemplate(
                pool_address="0xPoolB",
                token_in=pair.quote,
                token_out=pair.base,
                token_in_index=0,
            ),
        )


async def process_mempool(
    config: BotConfig,
    detector: OpportunityDetector,
    scorer: OpportunityScorer,
    executor: FlashbotsExecutor,
) -> None:
    streamer = MempoolStreamer(config)
    candidate_paths = list(build_candidate_paths(config))
    async for tx_hash in streamer.stream():
        LOGGER.debug("tx observed: %s", tx_hash)
        opportunities = await detector.detect(amount_in=10**18, candidate_paths=candidate_paths)
        ranked = scorer.rank(opportunities)
        if not ranked:
            continue
        best = ranked[0]
        LOGGER.info(
            "Opportunity profit %.4f ETH", best.profit / 10**18
        )
        # Left as a placeholder: craft bundle from opportunity legs
        dummy_tx = BundleTx(raw_tx="0xdeadbeef")
        current_block = await detector.rpc.web3.eth.block_number
        target_block = current_block + 2
        await executor.submit([dummy_tx], target_block)


async def main() -> None:
    config = BotConfig()
    rpc = RPCProvider(config)
    gas_price = await rpc.web3.eth.gas_price
    detector = OpportunityDetector(UniswapV2Client(rpc), gas_price_wei=int(gas_price))
    scorer = OpportunityScorer(config.ai_model_path)
    executor = FlashbotsExecutor(config)
    await process_mempool(config, detector, scorer, executor)


def run_bot() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run_bot()
