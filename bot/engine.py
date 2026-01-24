from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
import threading
import time
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .binance_client import BinanceClient
from .config import PairConfig
from .paribu_client import MissingEndpointError, ParibuClient, ParibuOrder
from .utils import clamp_min, format_decimal, round_down, round_up, to_decimal


@dataclass
class EngineSettings:
    order_qty: Decimal
    profit_percent: Decimal
    poll_interval: float
    leverage: int
    position_sync_interval: float
    dry_run: bool


@dataclass
class TrackedOrder:
    order_id: str
    side: str
    price: Decimal
    quantity: Decimal
    filled_qty: Decimal
    client_order_id: Optional[str]


class BotEngine:
    def __init__(
        self,
        pair: PairConfig,
        paribu: ParibuClient,
        binance_futures: BinanceClient,
        settings: EngineSettings,
        logger: Optional[logging.Logger] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._pair = pair
        self._paribu = paribu
        self._binance = binance_futures
        self._settings = settings
        self._logger = logger or logging.getLogger(__name__)
        self._log_callback = log_callback

        self._order_qty = self._normalize_qty(settings.order_qty)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._tracked_orders: Dict[str, TrackedOrder] = {}
        self._short_qty = Decimal("0")
        self._last_position_sync = 0.0
        self._client_id_counter = 0
        self._warned_no_client_id = False
        self._warned_no_open_orders = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        self._prepare_binance()
        self._log("Bot started.")
        while not self._stop_event.is_set():
            start = time.time()
            try:
                self._tick()
            except Exception as exc:  # pragma: no cover - defensive
                self._log(f"Tick error: {exc}", level="error")
            elapsed = time.time() - start
            sleep_time = max(0.0, self._settings.poll_interval - elapsed)
            self._stop_event.wait(sleep_time)
        self._log("Bot stopped.")

    def _tick(self) -> None:
        binance_price_tl = self._get_binance_tl_price()
        buy_prices, sell_prices = self._calculate_target_prices(binance_price_tl)
        self._log(
            f"Binance TL={binance_price_tl} buy={buy_prices} sell={sell_prices}",
            level="debug",
        )
        self._sync_position_if_needed()
        self._sync_orders(buy_prices, sell_prices)

    def _calculate_target_prices(self, binance_price_tl: Decimal) -> Tuple[List[Decimal], List[Decimal]]:
        profit_fraction = self._settings.profit_percent / Decimal("100")
        max_buy = round_down(binance_price_tl * (Decimal("1") - profit_fraction), self._pair.tick_size)
        min_sell = round_up(binance_price_tl * (Decimal("1") + profit_fraction), self._pair.tick_size)

        buy_prices = [max_buy - self._pair.tick_size * i for i in range(3)]
        sell_prices = [min_sell + self._pair.tick_size * i for i in range(3)]

        buy_prices = [price for price in buy_prices if price > 0]
        sell_prices = [price for price in sell_prices if price > 0]

        return buy_prices, sell_prices

    def _sync_orders(self, buy_prices: Iterable[Decimal], sell_prices: Iterable[Decimal]) -> None:
        open_orders = self._fetch_open_orders()
        managed_orders = self._filter_managed_orders(open_orders)
        if not managed_orders and self._tracked_orders:
            managed_orders = self._refresh_tracked_orders()
        self._update_tracked_orders(managed_orders)
        self._handle_fill_updates(managed_orders)

        desired = self._build_desired_orders(buy_prices, sell_prices)
        open_by_key: Dict[Tuple[str, Decimal], List[ParibuOrder]] = {}
        for order in managed_orders:
            key = (order.side, order.price)
            open_by_key.setdefault(key, []).append(order)

        keep_ids: set[str] = set()
        for side, price in desired:
            orders = open_by_key.get((side, price), [])
            if orders:
                keep_ids.add(orders[0].order_id)
                for extra in orders[1:]:
                    self._cancel_order(extra)
            else:
                self._place_order(side, price)

        for order in managed_orders:
            if order.order_id not in keep_ids:
                self._cancel_order(order)

    def _fetch_open_orders(self) -> List[ParibuOrder]:
        if self._settings.dry_run:
            return self._dry_run_open_orders()
        try:
            return self._paribu.get_open_orders(self._pair.paribu_symbol)
        except MissingEndpointError:
            if not self._warned_no_open_orders:
                self._warned_no_open_orders = True
                self._log("Open orders endpoint missing; using tracked orders only.", level="warning")
        except Exception as exc:
            self._log(f"Open orders fetch failed; using tracked orders: {exc}", level="warning")
        return self._refresh_tracked_orders()

    def _dry_run_open_orders(self) -> List[ParibuOrder]:
        orders: List[ParibuOrder] = []
        for tracked in self._tracked_orders.values():
            orders.append(
                ParibuOrder(
                    order_id=tracked.order_id,
                    client_order_id=tracked.client_order_id,
                    side=tracked.side,
                    price=tracked.price,
                    quantity=tracked.quantity,
                    filled_qty=tracked.filled_qty,
                    status="open",
                )
            )
        return orders

    def _refresh_tracked_orders(self) -> List[ParibuOrder]:
        open_orders: List[ParibuOrder] = []
        closed_states = {"filled", "done", "closed", "canceled", "cancelled"}
        for order_id in list(self._tracked_orders.keys()):
            try:
                order = self._paribu.get_order(self._pair.paribu_symbol, order_id)
            except Exception as exc:
                self._log(f"Order status fetch failed {order_id}: {exc}", level="warning")
                continue
            status = order.status.lower()
            if status in closed_states:
                self._tracked_orders.pop(order_id, None)
                continue
            open_orders.append(order)
        return open_orders

    def _build_desired_orders(self, buy_prices: Iterable[Decimal], sell_prices: Iterable[Decimal]) -> List[Tuple[str, Decimal]]:
        desired: List[Tuple[str, Decimal]] = []
        for price in buy_prices:
            desired.append(("buy", price))
        for price in sell_prices:
            desired.append(("sell", price))
        return desired

    def _place_order(self, side: str, price: Decimal) -> None:
        price_str = format_decimal(price, self._pair.tick_size)
        qty_str = format_decimal(self._order_qty, self._pair.qty_step)
        client_id = self._next_client_id(side)
        if self._settings.dry_run:
            order_id = f"dry-{side}-{price_str}"
            self._tracked_orders[order_id] = TrackedOrder(
                order_id=order_id,
                side=side,
                price=price,
                quantity=self._order_qty,
                filled_qty=Decimal("0"),
                client_order_id=client_id,
            )
            self._log(f"DRY RUN place {side} {price_str} qty={qty_str}")
            return
        order = self._paribu.place_limit_order(
            self._pair.paribu_symbol, side, price_str, qty_str, client_id
        )
        self._tracked_orders[order.order_id] = TrackedOrder(
            order_id=order.order_id,
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            filled_qty=order.filled_qty,
            client_order_id=order.client_order_id,
        )
        self._log(f"Placed {side} {price_str} qty={qty_str} id={order.order_id}")

    def _cancel_order(self, order: ParibuOrder) -> None:
        if self._settings.dry_run:
            self._tracked_orders.pop(order.order_id, None)
            self._log(f"DRY RUN cancel {order.order_id}")
            return
        self._paribu.cancel_order(self._pair.paribu_symbol, order.order_id)
        self._tracked_orders.pop(order.order_id, None)
        self._log(f"Canceled order {order.order_id}")

    def _filter_managed_orders(self, orders: List[ParibuOrder]) -> List[ParibuOrder]:
        if self._paribu.manage_all_orders:
            return orders
        prefix = self._paribu.client_order_id_prefix
        filtered = []
        for order in orders:
            if order.client_order_id and order.client_order_id.startswith(prefix):
                filtered.append(order)
        if orders and not filtered:
            if not self._warned_no_client_id:
                self._warned_no_client_id = True
                self._log(
                    "Open orders have no client IDs. Auto-managing all open orders. "
                    "Set manage_all_orders=true to silence this warning.",
                    level="warning",
                )
            return orders
        return filtered

    def _update_tracked_orders(self, orders: List[ParibuOrder]) -> None:
        for order in orders:
            tracked = self._tracked_orders.get(order.order_id)
            if tracked:
                tracked.price = order.price
                tracked.quantity = order.quantity
                tracked.filled_qty = order.filled_qty
                tracked.client_order_id = order.client_order_id
            else:
                self._tracked_orders[order.order_id] = TrackedOrder(
                    order_id=order.order_id,
                    side=order.side,
                    price=order.price,
                    quantity=order.quantity,
                    filled_qty=order.filled_qty,
                    client_order_id=order.client_order_id,
                )

    def _handle_fill_updates(self, open_orders: List[ParibuOrder]) -> None:
        open_by_id = {order.order_id: order for order in open_orders}
        for order_id, tracked in list(self._tracked_orders.items()):
            if order_id in open_by_id:
                current = open_by_id[order_id]
                self._apply_fill_delta(tracked, current.filled_qty)
                tracked.filled_qty = current.filled_qty
                continue

            try:
                final = self._paribu.get_order(self._pair.paribu_symbol, order_id)
            except Exception as exc:
                self._log(f"Order status fetch failed {order_id}: {exc}", level="warning")
                continue

            self._apply_fill_delta(tracked, final.filled_qty)
            if final.status.lower() in ("filled", "canceled", "cancelled", "closed"):
                self._tracked_orders.pop(order_id, None)

    def _apply_fill_delta(self, tracked: TrackedOrder, new_filled_qty: Decimal) -> None:
        delta = new_filled_qty - tracked.filled_qty
        if delta <= 0:
            return
        self._log(f"Fill detected {tracked.side} qty={delta}")
        self._hedge_fill(tracked.side, delta)

    def _hedge_fill(self, side: str, qty: Decimal) -> None:
        qty = clamp_min(qty, Decimal("0"))
        if qty <= 0:
            return

        if side == "buy":
            binance_side = "SELL"
            reduce_only = False
            self._short_qty += qty
            action = "open_short"
        else:
            binance_side = "BUY"
            reduce_only = True
            qty = min(qty, self._short_qty)
            if qty <= 0:
                self._log("No short position to close.", level="warning")
                return
            self._short_qty -= qty
            action = "close_short"

        if self._settings.dry_run:
            self._log(f"DRY RUN hedge {action} qty={qty}")
            return

        result = self._binance.market_order(
            self._pair.binance_futures_symbol,
            binance_side,
            qty,
            reduce_only=reduce_only,
        )
        self._log(
            f"Hedge {action} side={binance_side} qty={qty} "
            f"status={result.status} id={result.order_id}"
        )

    def _get_binance_tl_price(self) -> Decimal:
        futures_price = self._binance.get_futures_price(self._pair.binance_futures_symbol)
        usdt_try = self._binance.get_spot_price("USDTTRY")
        return futures_price * usdt_try

    def _normalize_qty(self, qty: Decimal) -> Decimal:
        qty = round_down(qty, self._pair.qty_step)
        if qty < self._pair.min_qty:
            raise ValueError(
                f"Order quantity {qty} is below minimum {self._pair.min_qty}."
            )
        return qty

    def _prepare_binance(self) -> None:
        if self._settings.dry_run:
            self._log("DRY RUN: skip Binance leverage/margin setup.")
            return
        self._binance.set_margin_type(self._pair.binance_futures_symbol, "CROSSED")
        self._binance.set_leverage(self._pair.binance_futures_symbol, self._settings.leverage)

    def _sync_position_if_needed(self) -> None:
        if self._settings.dry_run:
            return
        now = time.time()
        if now - self._last_position_sync < self._settings.position_sync_interval:
            return
        self._last_position_sync = now
        position_amt = self._binance.get_position_qty(self._pair.binance_futures_symbol)
        if position_amt < 0:
            self._short_qty = abs(position_amt)
        else:
            self._short_qty = Decimal("0")

    def _next_client_id(self, side: str) -> str:
        self._client_id_counter += 1
        prefix = self._paribu.client_order_id_prefix
        return f"{prefix}-{side[:1].upper()}-{int(time.time() * 1000)}-{self._client_id_counter}"

    def _log(self, message: str, level: str = "info") -> None:
        getattr(self._logger, level)(message)
        if self._log_callback:
            self._log_callback(message)
