from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

from .utils import to_decimal


@dataclass
class BinanceOrderResult:
    order_id: str
    status: str
    executed_qty: Decimal


class BinanceClient:
    def __init__(
        self,
        futures_base_url: str,
        spot_base_url: str,
        api_key: str,
        api_secret: str,
        recv_window_ms: int,
    ):
        self._futures_base_url = futures_base_url.rstrip("/")
        self._spot_base_url = spot_base_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret.encode("utf-8")
        self._recv_window_ms = recv_window_ms
        self._session = requests.Session()
        self._session.headers.update({"X-MBX-APIKEY": api_key})

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self._recv_window_ms
        query = urlencode(params, doseq=True)
        signature = hmac.new(self._api_secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
        params["signature"] = signature
        return params

    def _request(
        self,
        method: str,
        base_url: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Any:
        params = params or {}
        if signed:
            params = self._sign(params)
        url = f"{base_url}{path}"
        response = self._session.request(method, url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_futures_price(self, symbol: str) -> Decimal:
        data = self._request(
            "GET", self._futures_base_url, "/fapi/v1/ticker/price", {"symbol": symbol}
        )
        return to_decimal(data["price"])

    def get_spot_price(self, symbol: str) -> Decimal:
        data = self._request("GET", self._spot_base_url, "/api/v3/ticker/price", {"symbol": symbol})
        return to_decimal(data["price"])

    def set_leverage(self, symbol: str, leverage: int) -> None:
        self._request(
            "POST",
            self._futures_base_url,
            "/fapi/v1/leverage",
            {"symbol": symbol, "leverage": leverage},
            signed=True,
        )

    def set_margin_type(self, symbol: str, margin_type: str) -> None:
        try:
            self._request(
                "POST",
                self._futures_base_url,
                "/fapi/v1/marginType",
                {"symbol": symbol, "marginType": margin_type},
                signed=True,
            )
        except requests.HTTPError as exc:
            if exc.response is None:
                raise
            if exc.response.status_code == 400 and "No need to change margin type" in exc.response.text:
                return
            raise

    def market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        reduce_only: bool,
    ) -> BinanceOrderResult:
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": str(quantity),
            "reduceOnly": "true" if reduce_only else "false",
        }
        data = self._request(
            "POST", self._futures_base_url, "/fapi/v1/order", params, signed=True
        )
        return BinanceOrderResult(
            order_id=str(data.get("orderId", "")),
            status=str(data.get("status", "")),
            executed_qty=to_decimal(data.get("executedQty", "0")),
        )

    def get_position_qty(self, symbol: str) -> Decimal:
        data = self._request("GET", self._futures_base_url, "/fapi/v2/positionRisk", signed=True)
        for entry in data:
            if entry.get("symbol") == symbol:
                return to_decimal(entry.get("positionAmt", "0"))
        return Decimal("0")
