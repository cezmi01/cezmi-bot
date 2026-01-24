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
        self._warned_no_assets = False
        self._trade_seen: set[str] = set()
        self._last_trade_seen: Optional[str] = None
        self._trade_sync_ok = False
        self._order_trade_filled: Dict[str, Decimal] = {}
        self._base_asset = self._pair.paribu_symbol.split("_", 1)[0].upper()
        self._balance_last_total: Optional[Decimal] = None
        self._hedge_open_remainder = Decimal("0")
        self._hedge_close_remainder = Decimal("0")
        self._futures_multiplier = self._binance.get_futures_multiplier(
            self._pair.binance_futures_symbol
        )

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
        self._sync_position_if_needed()
        self._sync_trades_history()
        if not self._trade_sync_ok:
            self._sync_balance_hedge()
        self._sync_short_to_balance()
        try:
            binance_price_tl = self._get_binance_tl_price()
        except Exception as exc:
            self._log(f"Price fetch failed: {exc}", level="warning")
            self._sync_fills_only()
            return
        buy_prices, sell_prices = self._calculate_target_prices(binance_price_tl)
        self._log(
            f"Binance TL={binance_price_tl} buy={buy_prices} sell={sell_prices}",
            level="debug",
        )
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

    def _sync_fills_only(self) -> None:
        open_orders = self._fetch_open_orders()
        managed_orders = self._filter_managed_orders(open_orders)
        if not managed_orders and self._tracked_orders:
            managed_orders = self._refresh_tracked_orders()
        self._update_tracked_orders(managed_orders)
        self._handle_fill_updates(managed_orders)
        if not self._trade_sync_ok:
            self._sync_balance_hedge()
        self._sync_short_to_balance()

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
                self._order_trade_filled.pop(order_id, None)
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
        try:
            order = self._paribu.place_limit_order(
                self._pair.paribu_symbol, side, price_str, qty_str, client_id
            )
        except Exception as exc:
            self._log(f"Place order failed {side} {price_str}: {exc}", level="warning")
            return
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
                if order.filled_qty > tracked.filled_qty:
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
                if current.filled_qty > tracked.filled_qty:
                    self._apply_fill_delta(tracked, current.filled_qty)
                    tracked.filled_qty = current.filled_qty
                else:
                    # Some Paribu open-orders responses don't include partial fills.
                    self._refresh_order_status(tracked)
                continue

            self._refresh_order_status(tracked)

    def _refresh_order_status(self, tracked: TrackedOrder) -> None:
        try:
            final = self._paribu.get_order(self._pair.paribu_symbol, tracked.order_id)
        except Exception as exc:
            self._log(f"Order status fetch failed {tracked.order_id}: {exc}", level="warning")
            return

        if final.filled_qty > tracked.filled_qty:
            self._apply_fill_delta(tracked, final.filled_qty)
        if final.filled_qty > tracked.filled_qty:
            tracked.filled_qty = final.filled_qty
        if final.status.lower() in ("filled", "canceled", "cancelled", "closed"):
            self._tracked_orders.pop(tracked.order_id, None)
            self._order_trade_filled.pop(tracked.order_id, None)

    def _sync_trades_history(self) -> None:
        self._trade_sync_ok = False
        try:
            trades = self._paribu.get_trades_history(self._pair.paribu_symbol)
        except MissingEndpointError:
            return
        except Exception as exc:
            self._log(f"Trades history fetch failed: {exc}", level="warning")
            return

        self._trade_sync_ok = True
        if not trades:
            return

        trades.sort(key=lambda t: t.get("createdAt") or t.get("created_at") or "")
        if self._last_trade_seen is None:
            self._last_trade_seen = trades[-1].get("createdAt") or trades[-1].get("created_at")
            self._log("Trades history baseline set.", level="debug")
            return

        max_seen = self._last_trade_seen
        for trade in trades:
            created_at = trade.get("createdAt") or trade.get("created_at")
            if not created_at:
                continue
            if self._last_trade_seen and created_at < self._last_trade_seen:
                continue
            trade_key = (
                f"{created_at}|{trade.get('orderId','')}|{trade.get('direction','')}"
                f"|{trade.get('amount','')}|{trade.get('price','')}"
            )
            if trade_key in self._trade_seen:
                continue
            self._trade_seen.add(trade_key)
            if len(self._trade_seen) > 5000:
                self._trade_seen.clear()

            amount = to_decimal(trade.get("amount") or trade.get("qty") or "0")
            if amount <= 0:
                continue
            direction = str(trade.get("direction", "")).upper()
            if direction == "BUY":
                side = "buy"
            elif direction == "SELL":
                side = "sell"
            else:
                continue

            order_id = trade.get("orderId")
            if order_id:
                prev = self._order_trade_filled.get(order_id, Decimal("0"))
                new_total = prev + amount
                self._order_trade_filled[order_id] = new_total
                tracked = self._tracked_orders.get(order_id)
                if tracked and new_total > tracked.filled_qty:
                    self._apply_fill_delta(tracked, new_total)
                    tracked.filled_qty = new_total
                elif not tracked:
                    self._hedge_fill(side, amount)
            else:
                self._hedge_fill(side, amount)

            if max_seen is None or created_at > max_seen:
                max_seen = created_at
        self._last_trade_seen = max_seen

    def _sync_balance_hedge(self) -> None:
        total = self._get_balance_total()
        if total is None:
            return

        if self._balance_last_total is None:
            self._balance_last_total = total
            return

        delta = total - self._balance_last_total
        if delta == 0:
            return

        epsilon = self._pair.qty_step if self._pair.qty_step > 0 else Decimal("0.00000001")
        if abs(delta) < epsilon:
            return

        if delta > 0:
            self._log(f"Balance hedge buy delta={delta}", level="debug")
            self._hedge_fill("buy", delta)
        else:
            self._log(f"Balance hedge sell delta={abs(delta)}", level="debug")
            self._hedge_fill("sell", abs(delta))

        self._balance_last_total = total

    def _sync_short_to_balance(self) -> None:
        total = self._get_balance_total()
        if total is None:
            return
        if self._balance_last_total is None:
            self._balance_last_total = total

        target_short = total
        current_short = self._short_qty
        step = self._binance.get_futures_step(self._pair.binance_futures_symbol)
        min_delta = step * self._futures_multiplier
        if min_delta <= 0:
            min_delta = Decimal("0.00000001")
        delta = target_short - current_short
        if abs(delta) < min_delta:
            return

        if delta > 0:
            self._log(f"Balance sync open_short delta={delta}", level="debug")
            self._hedge_fill("buy", delta)
        else:
            self._log(f"Balance sync close_short delta={abs(delta)}", level="debug")
            self._hedge_fill("sell", abs(delta))

    def _get_balance_total(self) -> Optional[Decimal]:
        try:
            assets = self._paribu.get_assets()
        except MissingEndpointError:
            if not self._warned_no_assets:
                self._warned_no_assets = True
                self._log("Assets endpoint missing; balance hedge disabled.", level="warning")
            return None
        except Exception as exc:
            self._log(f"Assets fetch failed: {exc}", level="warning")
            return None

        total = None
        for asset in assets:
            currency = str(asset.get("currency", "")).upper()
            if currency == self._base_asset:
                total_raw = asset.get("total") or asset.get("available")
                if total_raw is not None:
                    total = to_decimal(total_raw)
                break
        return total

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
        if self._futures_multiplier <= 0:
            self._log("Invalid futures multiplier.", level="warning")
            return

        if side == "buy":
            binance_side = "SELL"
            reduce_only = False
            action = "open_short"
            total_contract = (qty / self._futures_multiplier) + self._hedge_open_remainder
        else:
            binance_side = "BUY"
            reduce_only = True
            total_contract = (qty / self._futures_multiplier) + self._hedge_close_remainder
            if self._short_qty <= 0:
                self._log("No short position to close.", level="warning")
                return
            action = "close_short"

        if action == "close_short":
            total_contract = min(total_contract, self._short_qty / self._futures_multiplier)
        hedge_contract = self._binance.adjust_futures_qty(
            self._pair.binance_futures_symbol, total_contract
        )
        if hedge_contract <= 0:
            self._log(f"Hedge {action} skipped; qty below step size.", level="warning")
            return
        hedge_coin = hedge_contract * self._futures_multiplier

        if self._settings.dry_run:
            if action == "open_short":
                self._short_qty += hedge_coin
                self._hedge_open_remainder = total_contract - hedge_contract
            else:
                self._short_qty = max(self._short_qty - hedge_coin, Decimal("0"))
                self._hedge_close_remainder = total_contract - hedge_contract
            self._log(f"DRY RUN hedge {action} qty={hedge_contract}")
            return

        try:
            result = self._binance.market_order(
                self._pair.binance_futures_symbol,
                binance_side,
                hedge_contract,
                reduce_only=reduce_only,
            )
        except Exception as exc:
            self._log(f"Hedge {action} failed: {exc}", level="error")
            if action == "open_short":
                self._hedge_open_remainder = total_contract
            else:
                self._hedge_close_remainder = total_contract
            return
        if action == "open_short":
            self._short_qty += hedge_coin
            self._hedge_open_remainder = total_contract - hedge_contract
        else:
            self._short_qty = max(self._short_qty - hedge_coin, Decimal("0"))
            self._hedge_close_remainder = total_contract - hedge_contract
        self._log(
            f"Hedge {action} side={binance_side} qty={hedge_contract} "
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
            self._short_qty = abs(position_amt) * self._futures_multiplier
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
