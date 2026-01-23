from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import base64
import hashlib
import hmac
import json
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


class MissingEndpointError(ValueError):
    pass


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

    def _signature(self, query: str = "", body: Optional[dict] = None) -> tuple[str, str]:
        request_body = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body else ""
        data_to_sign = f"{query}{request_body}"
        signature_bytes = hmac.new(
            self._config.api_secret.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_bytes).decode("utf-8")
        return signature, request_body

    def _request(
        self,
        method: str,
        endpoint_key: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Any:
        if endpoint_key not in self._config.endpoints:
            raise MissingEndpointError(f"Missing endpoint config for {endpoint_key}")
        params = params or {}
        headers: Dict[str, str] = {}

        endpoint = self._config.endpoints[endpoint_key]
        if isinstance(endpoint, dict):
            path = endpoint.get("path", "")
            method = endpoint.get("method", method)
            body_style = endpoint.get("body", self._config.post_style)
        else:
            path = endpoint
            body_style = self._config.post_style

        path_params = {key: value for key, value in params.items() if f"{{{key}}}" in path}
        if path_params:
            try:
                path = path.format(**path_params)
            except KeyError as exc:
                raise ValueError(f"Missing path param for {endpoint_key}: {exc}") from exc
            for key in path_params:
                params.pop(key, None)

        url = f"{self._config.base_url.rstrip('/')}{path}"
        request_kwargs: Dict[str, Any] = {"headers": headers, "timeout": 10}

        query_params: Dict[str, Any] = {}
        body_params: Optional[Dict[str, Any]] = None
        if method.upper() in ("POST", "DELETE") and body_style == "json":
            body_params = params
        else:
            query_params = params

        raw_body = ""
        if signed and self._config.auth_type != "none":
            query_string = urlencode(query_params, doseq=True) if query_params else ""
            signature, raw_body = self._signature(query=query_string, body=body_params)
            if self._config.key_header:
                headers[self._config.key_header] = self._config.api_key
            if self._config.sign_header:
                headers[self._config.sign_header] = signature
        elif body_params is not None:
            raw_body = json.dumps(body_params, separators=(",", ":"), ensure_ascii=False)

        if body_params is not None:
            headers.setdefault("Content-Type", "application/json")
            request_kwargs["data"] = raw_body

        if query_params:
            request_kwargs["params"] = query_params
        response = self._session.request(method, url, **request_kwargs)
        response.raise_for_status()
        return response.json()

    def get_orderbook(self, market: str, depth: int = 50) -> OrderBook:
        data = self._request("GET", "orderbook", {"market": market, "depth": depth}, signed=False)
        bids = [(to_decimal(bid[0]), to_decimal(bid[1])) for bid in data.get("bids", [])]
        asks = [(to_decimal(ask[0]), to_decimal(ask[1])) for ask in data.get("asks", [])]
        return OrderBook(bids=bids, asks=asks)

    def get_trades_history(self, market: str) -> List[Dict[str, Any]]:
        data = self._request(
            "GET",
            "trades_history",
            {"filter_market": market.lower()},
            signed=True,
        )
        trades = data.get("trades")
        if isinstance(trades, list):
            return trades
        return []

    def get_open_orders(self, market: str) -> List[ParibuOrder]:
        data = self._request("GET", "open_orders", {"market": market}, signed=True)
        orders_raw = data.get("orders", data)
        return [self._parse_order(item) for item in orders_raw]

    def place_limit_order(
        self,
        market: str,
        side: str,
        price: str,
        quantity: str,
        client_order_id: str,
    ) -> ParibuOrder:
        price_dec = to_decimal(price)
        qty_dec = to_decimal(quantity)
        total_value = int(price_dec * qty_dec)
        payload = {
            "market": market.lower(),
            "trade": side.lower(),
            "type": "limit",
            "price": float(price_dec),
            "amount": float(qty_dec),
            "total": total_value,
        }
        data = self._request("POST", "place_order", payload, signed=True)
        order_raw = data.get("order", data)
        return self._parse_order(order_raw)

    def cancel_order(self, market: str, order_id: str) -> None:
        self._request(
            "DELETE",
            "cancel_order",
            {"order_id": order_id},
            signed=True,
        )

    def get_order(self, market: str, order_id: str) -> ParibuOrder:
        data = self._request(
            "GET",
            "order_status",
            {"order_id": order_id},
            signed=True,
        )
        order_raw = data.get("order", data)
        return self._parse_order(order_raw)

    def _parse_order(self, raw: Dict[str, Any]) -> ParibuOrder:
        order_id = raw.get("id") or raw.get("uid") or raw.get("orderId") or raw.get("order_id")
        client_order_id = raw.get("clientOrderId") or raw.get("client_order_id")
        side_raw = raw.get("side") or raw.get("trade") or ""
        side = str(side_raw).lower()
        if side in ("bid", "buy"):
            side = "buy"
        elif side in ("ask", "sell"):
            side = "sell"

        price = to_decimal(raw.get("price", "0"))
        quantity = to_decimal(
            raw.get("origQty")
            or raw.get("quantity")
            or raw.get("amount")
            or raw.get("original_amount")
            or "0"
        )
        remaining = raw.get("remaining_amount") or raw.get("remainingAmount") or raw.get("leftAmount")
        if remaining is not None:
            remaining_qty = to_decimal(remaining)
            filled_qty = quantity - remaining_qty
        else:
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
