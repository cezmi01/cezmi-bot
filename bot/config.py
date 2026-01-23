from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import os
from typing import Any, Dict, List


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ParibuConfig:
    base_url: str
    api_key: str
    api_secret: str
    auth_type: str
    key_header: str
    sign_header: str
    signature_param: str | None
    timestamp_param: str | None
    recv_window_ms: int
    client_order_id_prefix: str
    post_style: str
    manage_all_orders: bool
    endpoints: Dict[str, Any]


@dataclass(frozen=True)
class BinanceConfig:
    futures_base_url: str
    spot_base_url: str
    api_key: str
    api_secret: str
    recv_window_ms: int


@dataclass(frozen=True)
class PairConfig:
    name: str
    paribu_symbol: str
    binance_futures_symbol: str
    tick_size: Decimal
    qty_step: Decimal
    min_qty: Decimal


@dataclass(frozen=True)
class AppConfig:
    paribu: ParibuConfig
    binance: BinanceConfig
    pairs: List[PairConfig]


def _resolve_env(value: Any, field_name: str) -> Any:
    if not isinstance(value, str):
        return value
    if not value.startswith("env:"):
        return value
    env_name = value[4:]
    env_value = os.getenv(env_name)
    if env_value is None or env_value == "":
        raise ConfigError(f"Missing environment variable: {env_name} for {field_name}")
    return env_value


def _load_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Invalid decimal for {field_name}: {value}") from exc


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    paribu_raw = raw.get("paribu", {})
    paribu = ParibuConfig(
        base_url=_resolve_env(paribu_raw.get("base_url"), "paribu.base_url"),
        api_key=_resolve_env(paribu_raw.get("api_key"), "paribu.api_key"),
        api_secret=_resolve_env(paribu_raw.get("api_secret"), "paribu.api_secret"),
        auth_type=paribu_raw.get("auth_type", "hmac_sha256_base64"),
        key_header=paribu_raw.get("key_header", "Authorization"),
        sign_header=paribu_raw.get("sign_header", "X-Signature"),
        signature_param=paribu_raw.get("signature_param"),
        timestamp_param=paribu_raw.get("timestamp_param"),
        recv_window_ms=int(paribu_raw.get("recv_window_ms", 0)),
        client_order_id_prefix=paribu_raw.get("client_order_id_prefix", "CBOT"),
        post_style=paribu_raw.get("post_style", "json"),
        manage_all_orders=bool(paribu_raw.get("manage_all_orders", False)),
        endpoints=dict(paribu_raw.get("endpoints", {})),
    )

    binance_raw = raw.get("binance", {})
    binance = BinanceConfig(
        futures_base_url=_resolve_env(
            binance_raw.get("futures_base_url"), "binance.futures_base_url"
        ),
        spot_base_url=_resolve_env(
            binance_raw.get("spot_base_url"), "binance.spot_base_url"
        ),
        api_key=_resolve_env(binance_raw.get("api_key"), "binance.api_key"),
        api_secret=_resolve_env(binance_raw.get("api_secret"), "binance.api_secret"),
        recv_window_ms=int(binance_raw.get("recv_window_ms", 5000)),
    )

    pairs = []
    for pair_raw in raw.get("pairs", []):
        pairs.append(
            PairConfig(
                name=pair_raw["name"],
                paribu_symbol=pair_raw["paribu_symbol"],
                binance_futures_symbol=pair_raw["binance_futures_symbol"],
                tick_size=_load_decimal(pair_raw["tick_size"], "pair.tick_size"),
                qty_step=_load_decimal(pair_raw["qty_step"], "pair.qty_step"),
                min_qty=_load_decimal(pair_raw["min_qty"], "pair.min_qty"),
            )
        )

    if not pairs:
        raise ConfigError("No pairs configured in config.json")

    return AppConfig(paribu=paribu, binance=binance, pairs=pairs)
