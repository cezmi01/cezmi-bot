import base64
import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import requests
from PySide6 import QtCore, QtWidgets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")

PARIBU_BASE_URL = "https://api.paribu.com"
BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_EXCHANGE_INFO_URL = "https://api.binance.com/api/v3/exchangeInfo"

LOG_RETENTION_SECONDS = 24 * 60 * 60
BINANCE_POLL_SECONDS = 1.0
ORDER_POLL_SECONDS = 1.0


@dataclass
class TrackedOrder:
    order_id: str
    market: str
    side: str
    price: float
    amount: float
    created_at: float
    partial_reported: bool = False
    full_reported: bool = False
    done: bool = False


@dataclass
class LogEntry:
    ts: float
    market: str
    side: str
    price: float
    amount: float
    status: str


class ConfigStore:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> Dict[str, str]:
        data: Dict[str, str] = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                data = {}

        return data

    def save(self, data: Dict[str, str]) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)


class LogStore:
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    def add(self, entry: LogEntry) -> None:
        date_key = datetime.fromtimestamp(entry.ts).strftime("%Y-%m-%d")
        path = os.path.join(self.log_dir, f"{date_key}.jsonl")
        payload = {
            "ts": entry.ts,
            "market": entry.market,
            "side": entry.side,
            "price": entry.price,
            "amount": entry.amount,
            "status": entry.status,
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n")

    def prune(self, max_age_seconds: int) -> None:
        cutoff = time.time() - max_age_seconds
        if not os.path.isdir(self.log_dir):
            return

        for filename in os.listdir(self.log_dir):
            if not filename.endswith(".jsonl"):
                continue
            path = os.path.join(self.log_dir, filename)
            keep_lines: List[str] = []
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            payload = json.loads(line.strip())
                            if float(payload.get("ts", 0)) >= cutoff:
                                keep_lines.append(line)
                        except Exception:
                            continue
            except FileNotFoundError:
                continue

            if not keep_lines:
                try:
                    os.remove(path)
                except OSError:
                    pass
            else:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.writelines(keep_lines)


class ParibuClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = PARIBU_BASE_URL):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")

    def _signature(self, query: str = "", body: Optional[dict] = None) -> tuple[str, str]:
        request_body = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body else ""
        data_to_sign = f"{query}{request_body}"
        signature_bytes = hmac.new(
            self.api_secret.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_bytes).decode("utf-8")
        return signature, request_body

    def create_limit_order(self, market: str, side: str, amount: float, price: float) -> Dict[str, Any]:
        url = f"{self.base_url}/order"
        body = {
            "market": market,
            "trade": side,
            "type": "limit",
            "price": price,
            "amount": amount,
            "total": int(price * amount),
        }
        signature, raw_body = self._signature(body=body)
        headers = {"Authorization": self.api_key, "X-Signature": signature, "Content-Type": "application/json"}
        response = requests.post(url, headers=headers, data=raw_body, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"Paribu order error {response.status_code}: {response.text}")
        return response.json()

    def get_order(self, order_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/order/{order_id}"
        signature, _ = self._signature()
        headers = {"Authorization": self.api_key, "X-Signature": signature, "Content-Type": "application/json"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"Paribu order status error {response.status_code}: {response.text}")
        return response.json()


def parse_market_base(market: str) -> Optional[str]:
    cleaned = market.strip().lower()
    if not cleaned:
        return None
    if "_" in cleaned:
        base = cleaned.split("_", 1)[0]
    elif "-" in cleaned:
        base = cleaned.split("-", 1)[0]
    else:
        base = cleaned
        if base.endswith("try"):
            base = base[: -len("try")]
        elif base.endswith("tl"):
            base = base[: -len("tl")]
    base = base.upper()
    if not base:
        return None
    return base


def fetch_binance_price(symbol: str) -> float:
    response = requests.get(BINANCE_PRICE_URL, params={"symbol": symbol}, timeout=5)
    response.raise_for_status()
    payload = response.json()
    return float(payload["price"])


class BinanceSymbolResolver:
    def __init__(self, refresh_seconds: int = 6 * 60 * 60):
        self._lock = threading.Lock()
        self._base_map: Dict[str, Dict[str, str]] = {}
        self._last_fetch = 0.0
        self._refresh_seconds = refresh_seconds

    def _fetch_exchange_info(self) -> Dict[str, Dict[str, str]]:
        response = requests.get(BINANCE_EXCHANGE_INFO_URL, timeout=10)
        response.raise_for_status()
        payload = response.json()
        mapping: Dict[str, Dict[str, str]] = {}
        for symbol_info in payload.get("symbols", []):
            if symbol_info.get("status") != "TRADING":
                continue
            if symbol_info.get("isSpotTradingAllowed") is False:
                continue
            base = symbol_info.get("baseAsset")
            quote = symbol_info.get("quoteAsset")
            symbol = symbol_info.get("symbol")
            if not base or not quote or not symbol:
                continue
            base_map = mapping.setdefault(base.upper(), {})
            base_map[quote.upper()] = symbol.upper()
        return mapping

    def _ensure_loaded(self) -> None:
        now = time.time()
        with self._lock:
            needs_refresh = not self._base_map or (now - self._last_fetch) > self._refresh_seconds
        if not needs_refresh:
            return
        mapping = self._fetch_exchange_info()
        with self._lock:
            self._base_map = mapping
            self._last_fetch = now

    def resolve(self, base_asset: str, preferred_quotes: Optional[List[str]] = None) -> Optional[str]:
        if not base_asset:
            return None
        self._ensure_loaded()
        preferred = preferred_quotes or ["USDT", "TRY", "USDC", "BUSD", "BTC", "ETH"]
        base = base_asset.upper()
        with self._lock:
            quotes = self._base_map.get(base, {})
        for quote in preferred:
            symbol = quotes.get(quote)
            if symbol:
                return symbol
        if quotes:
            return next(iter(quotes.values()))
        return None


def _find_value(data: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data:
            return data[key]
    nested = data.get("data")
    if isinstance(nested, dict):
        for key in keys:
            if key in nested:
                return nested[key]
    return None


def _parse_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _status_to_state(status_value: Any) -> str:
    if status_value is None:
        return ""
    return str(status_value).strip().lower()


class OrderMonitorThread(QtCore.QThread):
    log_ready = QtCore.Signal(object)
    status_error = QtCore.Signal(str)

    def __init__(self, client_getter: Callable[[], Optional[ParibuClient]], poll_interval: float = ORDER_POLL_SECONDS):
        super().__init__()
        self._client_getter = client_getter
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._orders: List[TrackedOrder] = []
        self._stop = threading.Event()

    def add_order(self, order: TrackedOrder) -> None:
        with self._lock:
            self._orders.append(order)

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            client = self._client_getter()
            if client is None:
                self._stop.wait(self._poll_interval)
                continue

            with self._lock:
                orders = list(self._orders)

            for order in orders:
                if order.done:
                    continue
                try:
                    payload = client.get_order(order.order_id)
                except Exception as exc:
                    self.status_error.emit(str(exc))
                    continue

                status_value = _find_value(payload, ["status"])
                remaining_value = _find_value(
                    payload, ["remaining_amount", "remainingAmount", "leftAmount", "left_amount"]
                )
                amount_value = _find_value(payload, ["amount", "original_amount", "origQty", "quantity"])

                status = _status_to_state(status_value)
                remaining = _parse_float(remaining_value)
                total_amount = _parse_float(amount_value) or order.amount

                if status in {"canceled", "cancelled"}:
                    order.done = True
                    continue

                if remaining is not None:
                    executed = max(total_amount - remaining, 0.0)
                    if 0 < executed < total_amount and not order.partial_reported:
                        entry = LogEntry(
                            ts=time.time(),
                            market=order.market,
                            side=order.side,
                            price=order.price,
                            amount=executed,
                            status="Kismi",
                        )
                        self.log_ready.emit(entry)
                        order.partial_reported = True

                    if remaining <= 0 and not order.full_reported:
                        entry = LogEntry(
                            ts=time.time(),
                            market=order.market,
                            side=order.side,
                            price=order.price,
                            amount=total_amount,
                            status="Tam",
                        )
                        self.log_ready.emit(entry)
                        order.full_reported = True
                        order.done = True
                else:
                    if status in {"closed", "filled", "done"} and not order.full_reported:
                        entry = LogEntry(
                            ts=time.time(),
                            market=order.market,
                            side=order.side,
                            price=order.price,
                            amount=total_amount,
                            status="Tam",
                        )
                        self.log_ready.emit(entry)
                        order.full_reported = True
                        order.done = True

            with self._lock:
                self._orders = [order for order in self._orders if not order.done]

            self._stop.wait(self._poll_interval)


class BinancePriceWorker(QtCore.QThread):
    price_ready = QtCore.Signal(str, float)
    symbol_ready = QtCore.Signal(str)
    price_error = QtCore.Signal(str)

    def __init__(self, poll_interval: float = BINANCE_POLL_SECONDS):
        super().__init__()
        self._poll_interval = poll_interval
        self._market: Optional[str] = None
        self._symbol: Optional[str] = None
        self._resolver = BinanceSymbolResolver()
        self._stop = threading.Event()

    def set_market(self, market: Optional[str]) -> None:
        self._market = market
        self._symbol = None

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            market = self._market or ""
            base = parse_market_base(market)
            symbol = self._symbol
            if base and symbol is None:
                try:
                    resolved = self._resolver.resolve(base)
                except Exception as exc:
                    self.price_error.emit(str(exc))
                    resolved = None
                if resolved != symbol:
                    symbol = resolved
                    self._symbol = resolved
                    self.symbol_ready.emit(resolved or "")

            if symbol:
                try:
                    price = fetch_binance_price(symbol)
                    self.price_ready.emit(symbol, price)
                except Exception as exc:
                    self.price_error.emit(str(exc))
            self._stop.wait(self._poll_interval)


class OrderSenderThread(threading.Thread):
    def __init__(
        self,
        client_getter: Callable[[], Optional[ParibuClient]],
        market: str,
        side: str,
        price: float,
        amount: float,
        repeat: int,
        interval_ms: int,
        stop_event: threading.Event,
        on_order_created: Callable[[TrackedOrder], None],
        on_error: Callable[[str], None],
        on_done: Callable[[], None],
    ):
        super().__init__(daemon=True)
        self.client_getter = client_getter
        self.market = market
        self.side = side
        self.price = price
        self.amount = amount
        self.repeat = repeat
        self.interval_ms = interval_ms
        self.stop_event = stop_event
        self.on_order_created = on_order_created
        self.on_error = on_error
        self.on_done = on_done

    def run(self) -> None:
        try:
            count = 0
            while not self.stop_event.is_set():
                if self.repeat > 0 and count >= self.repeat:
                    break

                client = self.client_getter()
                if client is None:
                    self.on_error("Paribu ayarlari eksik.")
                    break

                try:
                    payload = client.create_limit_order(
                        market=self.market,
                        side=self.side,
                        amount=self.amount,
                        price=self.price,
                    )
                except Exception as exc:
                    self.on_error(str(exc))
                    break

                order_id = None
                if isinstance(payload, dict):
                    order_id = payload.get("uid") or payload.get("order_id") or payload.get("id")
                    if not order_id and isinstance(payload.get("data"), dict):
                        order_id = payload["data"].get("id") or payload["data"].get("uid")

                if not order_id:
                    self.on_error("Paribu order id okunamadi.")
                    break

                tracked = TrackedOrder(
                    order_id=str(order_id),
                    market=self.market,
                    side=self.side,
                    price=self.price,
                    amount=self.amount,
                    created_at=time.time(),
                )
                self.on_order_created(tracked)
                count += 1

                if self.interval_ms > 0:
                    if self.stop_event.wait(self.interval_ms / 1000.0):
                        break
        finally:
            self.on_done()


class MainWindow(QtWidgets.QMainWindow):
    status_message = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paribu Manuel Bot")
        self.resize(980, 720)

        self.config_store = ConfigStore(CONFIG_PATH)
        self.config = self.config_store.load()
        self.log_store = LogStore(LOG_DIR)

        self.paribu_client: Optional[ParibuClient] = None
        self._refresh_paribu_client()

        self.stop_event = threading.Event()
        self.sender_lock = threading.Lock()
        self.active_senders = 0
        self.sending = False

        self.price_inputs: List[QtWidgets.QDoubleSpinBox] = []
        self.amount_inputs: List[QtWidgets.QDoubleSpinBox] = []
        self.repeat_inputs: List[QtWidgets.QSpinBox] = []
        self.interval_inputs: List[QtWidgets.QSpinBox] = []

        self.status_message.connect(self._set_status)

        self._build_ui()

        self.order_monitor = OrderMonitorThread(self._get_paribu_client)
        self.order_monitor.log_ready.connect(self.add_log_entry)
        self.order_monitor.status_error.connect(self._set_status)
        self.order_monitor.start()

        self.binance_worker = BinancePriceWorker()
        self.binance_worker.price_ready.connect(self._update_binance_price)
        self.binance_worker.symbol_ready.connect(self._update_binance_symbol_label)
        self.binance_worker.price_error.connect(self._set_status)
        self.binance_worker.start()

        self.cleanup_timer = QtCore.QTimer(self)
        self.cleanup_timer.timeout.connect(self._cleanup_logs)
        self.cleanup_timer.start(5 * 60 * 1000)

        self._cleanup_logs()
        self._update_binance_symbol()

    def closeEvent(self, event) -> None:
        self.stop_event.set()
        if self.binance_worker:
            self.binance_worker.stop()
            self.binance_worker.wait(2000)
        if self.order_monitor:
            self.order_monitor.stop()
            self.order_monitor.wait(2000)
        super().closeEvent(event)

    def _build_ui(self) -> None:
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._build_setup_tab(), "Setup")
        tabs.addTab(self._build_settings_tab(), "Ayarlar")
        tabs.addTab(self._build_manual_tab(), "Manuel")
        self.setCentralWidget(tabs)

    def _build_setup_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        label = QtWidgets.QLabel("Setup")
        layout.addWidget(label)
        layout.addStretch()
        return widget

    def _build_settings_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.paribu_key_input = QtWidgets.QLineEdit()
        self.paribu_secret_input = QtWidgets.QLineEdit()
        self.paribu_secret_input.setEchoMode(QtWidgets.QLineEdit.Password)

        self.paribu_key_input.setText(self.config.get("paribu_api_key", ""))
        self.paribu_secret_input.setText(self.config.get("paribu_api_secret", ""))

        layout.addRow("Paribu API Key", self.paribu_key_input)
        layout.addRow("Paribu API Secret", self.paribu_secret_input)

        save_button = QtWidgets.QPushButton("Kaydet")
        save_button.clicked.connect(self._save_settings)
        layout.addRow(save_button)
        return widget

    def _build_manual_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(widget)

        form_group = QtWidgets.QGroupBox("Manuel Emir")
        form_layout = QtWidgets.QFormLayout(form_group)

        self.market_input = QtWidgets.QLineEdit()
        self.market_input.setPlaceholderText("ada_tl")
        self.market_input.textChanged.connect(self._update_binance_symbol)
        form_layout.addRow("Market", self.market_input)

        side_layout = QtWidgets.QHBoxLayout()
        self.side_buy = QtWidgets.QRadioButton("Al")
        self.side_sell = QtWidgets.QRadioButton("Sat")
        self.side_buy.setChecked(True)
        side_layout.addWidget(self.side_buy)
        side_layout.addWidget(self.side_sell)
        side_layout.addStretch()
        form_layout.addRow("Islem", side_layout)

        outer.addWidget(form_group)
        outer.addWidget(self._build_order_grid())
        outer.addLayout(self._build_action_row())
        outer.addWidget(self._build_log_table())
        outer.addWidget(self._build_status_row())
        return widget

    def _build_order_grid(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Emirler (6 Sutun)")
        grid = QtWidgets.QGridLayout(group)

        headers = ["1", "2", "3", "4", "5", "6"]
        grid.addWidget(QtWidgets.QLabel(""), 0, 0)
        for idx, name in enumerate(headers, start=1):
            label = QtWidgets.QLabel(name)
            label.setAlignment(QtCore.Qt.AlignCenter)
            grid.addWidget(label, 0, idx)

        row_defs = [
            ("Fiyat", self.price_inputs, self._make_price_input),
            ("Miktar", self.amount_inputs, self._make_amount_input),
            ("Tekrar", self.repeat_inputs, self._make_repeat_input),
            ("Aralik (ms)", self.interval_inputs, self._make_interval_input),
        ]

        for row_index, (label, bucket, factory) in enumerate(row_defs, start=1):
            grid.addWidget(QtWidgets.QLabel(label), row_index, 0)
            for col in range(6):
                widget = factory()
                bucket.append(widget)
                grid.addWidget(widget, row_index, col + 1)

        return group

    def _build_action_row(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()

        self.send_button = QtWidgets.QPushButton("GONDER")
        self.send_button.clicked.connect(self._on_send)
        self.stop_button = QtWidgets.QPushButton("STOP")
        self.stop_button.clicked.connect(self._on_stop)

        self.binance_symbol_label = QtWidgets.QLabel("Binance Sembol: -")
        self.binance_price_label = QtWidgets.QLabel("Binance Fiyat: -")

        row.addWidget(self.send_button)
        row.addWidget(self.stop_button)
        row.addStretch()
        row.addWidget(self.binance_symbol_label)
        row.addWidget(self.binance_price_label)
        return row

    def _build_log_table(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Manuel Satis Listesi")
        layout = QtWidgets.QVBoxLayout(group)
        self.log_table = QtWidgets.QTableWidget(0, 6)
        self.log_table.setHorizontalHeaderLabels(
            ["Tarih/Saat", "Coin", "Islem", "Fiyat", "Miktar", "Durum"]
        )
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.log_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.log_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.log_table)
        return group

    def _build_status_row(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        self.status_label = QtWidgets.QLabel("")
        layout.addWidget(self.status_label)
        return widget

    def _make_price_input(self) -> QtWidgets.QDoubleSpinBox:
        box = QtWidgets.QDoubleSpinBox()
        box.setDecimals(8)
        box.setRange(0, 1_000_000_000)
        box.setSingleStep(0.01)
        return box

    def _make_amount_input(self) -> QtWidgets.QDoubleSpinBox:
        box = QtWidgets.QDoubleSpinBox()
        box.setDecimals(8)
        box.setRange(0, 1_000_000_000)
        box.setSingleStep(0.01)
        return box

    def _make_repeat_input(self) -> QtWidgets.QSpinBox:
        box = QtWidgets.QSpinBox()
        box.setRange(1, 10)
        box.setValue(1)
        return box

    def _make_interval_input(self) -> QtWidgets.QSpinBox:
        box = QtWidgets.QSpinBox()
        box.setRange(0, 60_000_000)
        box.setValue(80)
        return box

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _save_settings(self) -> None:
        self.config = {
            "paribu_api_key": self.paribu_key_input.text().strip(),
            "paribu_api_secret": self.paribu_secret_input.text().strip(),
        }
        self.config_store.save(self.config)
        self._refresh_paribu_client()
        self.status_message.emit("Ayarlar kaydedildi.")

    def _refresh_paribu_client(self) -> None:
        key = self.config.get("paribu_api_key", "").strip()
        secret = self.config.get("paribu_api_secret", "").strip()
        if key and secret:
            self.paribu_client = ParibuClient(key, secret)
        else:
            self.paribu_client = None

    def _get_paribu_client(self) -> Optional[ParibuClient]:
        return self.paribu_client

    def _on_send(self) -> None:
        if self.sending:
            self.status_message.emit("Zaten calisiyor. Stop ile durdurun.")
            return

        market = self.market_input.text().strip()
        if not market:
            self.status_message.emit("Market giriniz.")
            return

        side = "buy" if self.side_buy.isChecked() else "sell"

        self.stop_event = threading.Event()
        self.active_senders = 0
        self.sending = True

        has_any = False
        for idx in range(6):
            price = float(self.price_inputs[idx].value())
            amount = float(self.amount_inputs[idx].value())
            repeat = int(self.repeat_inputs[idx].value())
            interval_ms = int(self.interval_inputs[idx].value())

            if price <= 0 or amount <= 0:
                continue

            has_any = True
            self._start_sender(
                market=market,
                side=side,
                price=price,
                amount=amount,
                repeat=repeat,
                interval_ms=interval_ms,
            )

        if not has_any:
            self.sending = False
            self.status_message.emit("En az bir sutun icin fiyat ve miktar giriniz.")
            return

        self.status_message.emit("Emir gonderimi basladi.")

    def _start_sender(
        self,
        market: str,
        side: str,
        price: float,
        amount: float,
        repeat: int,
        interval_ms: int,
    ) -> None:
        def on_order_created(tracked: TrackedOrder) -> None:
            self.order_monitor.add_order(tracked)

        def on_error(message: str) -> None:
            self.status_message.emit(message)

        def on_done() -> None:
            with self.sender_lock:
                self.active_senders -= 1
                if self.active_senders <= 0:
                    self.sending = False
                    self.status_message.emit("Emir gonderimi durdu.")

        with self.sender_lock:
            self.active_senders += 1

        sender = OrderSenderThread(
            client_getter=self._get_paribu_client,
            market=market,
            side=side,
            price=price,
            amount=amount,
            repeat=repeat,
            interval_ms=interval_ms,
            stop_event=self.stop_event,
            on_order_created=on_order_created,
            on_error=on_error,
            on_done=on_done,
        )
        sender.start()

    def _on_stop(self) -> None:
        if self.stop_event:
            self.stop_event.set()
            self.status_message.emit("Stop istendi. Yeni emir gonderilmeyecek.")

    def _update_binance_symbol(self) -> None:
        base = parse_market_base(self.market_input.text())
        if base:
            self.binance_symbol_label.setText(f"Binance Sembol: {base}")
        else:
            self.binance_symbol_label.setText("Binance Sembol: -")
        self.binance_worker.set_market(self.market_input.text())

    def _update_binance_symbol_label(self, symbol: str) -> None:
        if symbol:
            self.binance_symbol_label.setText(f"Binance Sembol: {symbol}")
        else:
            self.binance_symbol_label.setText("Binance Sembol: Bulunamadi")

    def _update_binance_price(self, symbol: str, price: float) -> None:
        self.binance_price_label.setText(f"Binance Fiyat: {price:.6f}")

    def add_log_entry(self, entry: LogEntry) -> None:
        self.log_store.add(entry)

        row = self.log_table.rowCount()
        self.log_table.insertRow(row)
        ts_text = datetime.fromtimestamp(entry.ts).strftime("%Y-%m-%d %H:%M:%S")
        side_text = "Al" if entry.side == "buy" else "Sat"

        values = [
            ts_text,
            entry.market,
            side_text,
            f"{entry.price:.8f}",
            f"{entry.amount:.8f}",
            entry.status,
        ]

        for col, value in enumerate(values):
            item = QtWidgets.QTableWidgetItem(value)
            if col == 0:
                item.setData(QtCore.Qt.UserRole, entry.ts)
            self.log_table.setItem(row, col, item)

        self._prune_ui_entries()

    def _cleanup_logs(self) -> None:
        self.log_store.prune(LOG_RETENTION_SECONDS)
        self._prune_ui_entries()

    def _prune_ui_entries(self) -> None:
        cutoff = time.time() - LOG_RETENTION_SECONDS
        rows_to_remove = []
        for row in range(self.log_table.rowCount()):
            item = self.log_table.item(row, 0)
            if not item:
                continue
            ts_value = item.data(QtCore.Qt.UserRole)
            if ts_value is None:
                continue
            try:
                ts_float = float(ts_value)
            except Exception:
                continue
            if ts_float < cutoff:
                rows_to_remove.append(row)

        for row in reversed(rows_to_remove):
            self.log_table.removeRow(row)


def main() -> None:
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
