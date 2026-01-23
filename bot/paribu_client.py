from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from .config import ParibuConfig
from .utils import to_decimal


@dataclass
class ParibuOrder:
    order_id: str
    client_order_id: Optional[str]
    side: str
    price: Decimal
    quantity: Decimal
    filled_qty: Decimal
    status: str


@dataclass
class OrderBook:
    bids: List[tuple[Decimal, Decimal]]
    asks: List[tuple[Decimal, Decimal]]


class ParibuClient:
    def __init__(self, config: ParibuConfig):
        self._config = config
        self._session = requests.Session()

    @property
    def client_order_id_prefix(self) -> str:
        return self._config.client_order_id_prefix

    @property
    def manage_all_orders(self) -> bool:
        return self._config.manage_all_orders

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if self._config.timestamp_param:
            params[self._config.timestamp_param] = int(time.time() * 1000)
        if self._config.recv_window_ms:
            params["recvWindow"] = self._config.recv_window_ms
        query = urlencode(params, doseq=True)
        signature = hmac.new(
            self._config.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if self._config.signature_param:
            params[self._config.signature_param] = signature
        return params, signature

    def _request(
        self,
        method: str,
        endpoint_key: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Any:
        if endpoint_key not in self._config.endpoints:
            raise ValueError(f"Missing endpoint config for {endpoint_key}")
        params = params or {}
        headers: Dict[str, str] = {}
        if signed and self._config.auth_type != "none":
            params, signature = self._sign(params)
            if self._config.key_header:
                headers[self._config.key_header] = self._config.api_key
            if self._config.sign_header and not self._config.signature_param:
                headers[self._config.sign_header] = signature

        endpoint = self._config.endpoints[endpoint_key]
        if isinstance(endpoint, dict):
            path = endpoint.get("path", "")
            method = endpoint.get("method", method)
            body_style = endpoint.get("body", self._config.post_style)
        else:
            path = endpoint
            body_style = self._config.post_style

        url = f"{self._config.base_url.rstrip('/')}{path}"
        request_kwargs = {"headers": headers, "timeout": 10}
        if method.upper() in ("POST", "DELETE") and body_style == "json":
            request_kwargs["json"] = params
        else:
            request_kwargs["params"] = params
        response = self._session.request(method, url, **request_kwargs)
        response.raise_for_status()
        return response.json()

    def get_orderbook(self, symbol: str, limit: int = 50) -> OrderBook:
        data = self._request("GET", "orderbook", {"symbol": symbol, "limit": limit}, signed=False)
        bids = [(to_decimal(bid[0]), to_decimal(bid[1])) for bid in data.get("bids", [])]
        asks = [(to_decimal(ask[0]), to_decimal(ask[1])) for ask in data.get("asks", [])]
        return OrderBook(bids=bids, asks=asks)

    def get_open_orders(self, symbol: str) -> List[ParibuOrder]:
        data = self._request("GET", "open_orders", {"symbol": symbol}, signed=True)
        orders_raw = data.get("orders", data)
        return [self._parse_order(item) for item in orders_raw]

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: str,
        quantity: str,
        client_order_id: str,
    ) -> ParibuOrder:
        payload = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "price": price,
            "quantity": quantity,
            "clientOrderId": client_order_id,
        }
        data = self._request("POST", "place_order", payload, signed=True)
        order_raw = data.get("order", data)
        return self._parse_order(order_raw)

    def cancel_order(self, symbol: str, order_id: str) -> None:
        self._request("DELETE", "cancel_order", {"symbol": symbol, "orderId": order_id}, signed=True)

    def get_order(self, symbol: str, order_id: str) -> ParibuOrder:
        data = self._request("GET", "order_status", {"symbol": symbol, "orderId": order_id}, signed=True)
        order_raw = data.get("order", data)
        return self._parse_order(order_raw)

    def _parse_order(self, raw: Dict[str, Any]) -> ParibuOrder:
        order_id = raw.get("id") or raw.get("orderId") or raw.get("order_id")
        client_order_id = raw.get("clientOrderId") or raw.get("client_order_id")
        side_raw = raw.get("side", "")
        side = str(side_raw).lower()
        if side in ("bid", "buy"):
            side = "buy"
        elif side in ("ask", "sell"):
            side = "sell"

        price = to_decimal(raw.get("price", "0"))
        quantity = to_decimal(raw.get("origQty") or raw.get("quantity") or raw.get("amount") or "0")
        filled_qty = to_decimal(
            raw.get("executedQty") or raw.get("filledQty") or raw.get("filled_quantity") or "0"
        )
        status = str(raw.get("status", raw.get("state", "")))

        return ParibuOrder(
            order_id=str(order_id),
            client_order_id=client_order_id,
            side=side,
            price=price,
            quantity=quantity,
            filled_qty=filled_qty,
            status=status,
        )
