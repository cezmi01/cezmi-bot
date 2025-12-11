"""Configuration helpers for the MEV bot."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TokenPair(BaseModel):
    """Token pair that will be monitored for triangular arbitrage."""

    base: str = Field(..., description="Token address of the base asset")
    quote: str = Field(..., description="Token address of the quote asset")
    min_profit_bps: int = Field(
        5,
        ge=1,
        le=10_000,
        description="Minimum profit in basis points to consider an opportunity",
    )


class BotConfig(BaseSettings):
    """Environment-aware settings."""

    rpc_url: str = Field(..., description="HTTPS RPC endpoint")
    ws_url: str | None = Field(None, description="Websocket RPC endpoint for mempool")
    flashbots_relay: str = Field(
        "https://relay.flashbots.net",
        description="Flashbots relay endpoint",
    )
    private_key: str = Field(..., description="Bot signing key")
    bundle_signer_key: str | None = Field(
        None, description="Optional Flashbots bundle signer key"
    )
    account_address: str = Field(..., description="EOA that sends bundles")
    target_pairs: List[TokenPair] = Field(default_factory=list)
    gas_limit: int = Field(800_000, ge=200_000, description="Gas limit per bundle")
    max_slippage_bps: int = Field(30, ge=1, le=500, description="Allowed slippage")
    db_path: Path = Field(Path("data/opportunities.db"), description="SQLite path")
    ai_model_path: Path = Field(
        Path("models/opportunity_ranker.pkl"), description="ML model file"
    )
    health_port: int = Field(8080, description="Port for health checks")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MEV_", extra="allow")

    def require_ws_url(self) -> str:
        """Return websocket endpoint or raise to fail fast."""

        if not self.ws_url:
            msg = "ws_url must be configured for mempool listening"
            raise ValueError(msg)
        return self.ws_url
