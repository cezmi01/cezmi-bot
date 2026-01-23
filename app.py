from __future__ import annotations

import argparse
from dataclasses import replace
from decimal import Decimal
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict

from bot.binance_client import BinanceClient
from bot.config import ConfigError, load_config
from bot.engine import BotEngine, EngineSettings
from bot.paribu_client import ParibuClient

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("cezmi-bot")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, "bot.log"))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


class SettingsStore:
    def __init__(self, path: str) -> None:
        self._path = path

    def load(self) -> Dict[str, str]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(key): str(value) for key, value in data.items()}

    def save(self, data: Dict[str, str]) -> None:
        with open(self._path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=True)


def _resolve_api_keys(config, api_settings: Dict[str, str]) -> tuple[str, str, str, str]:
    paribu_key = (api_settings.get("paribu_api_key") or config.paribu.api_key or "").strip()
    paribu_secret = (api_settings.get("paribu_api_secret") or config.paribu.api_secret or "").strip()
    binance_key = (api_settings.get("binance_api_key") or config.binance.api_key or "").strip()
    binance_secret = (api_settings.get("binance_api_secret") or config.binance.api_secret or "").strip()

    missing = []
    if not paribu_key or not paribu_secret:
        missing.append("Paribu API key/secret")
    if not binance_key or not binance_secret:
        missing.append("Binance API key/secret")
    if missing:
        raise ConfigError("Eksik API anahtari: " + ", ".join(missing))
    return paribu_key, paribu_secret, binance_key, binance_secret


def build_bot(
    config_path: str,
    pair_name: str,
    settings: EngineSettings,
    logger: logging.Logger,
    log_cb,
    api_settings: Dict[str, str],
):
    config = load_config(config_path)
    pair = next((p for p in config.pairs if p.name == pair_name), None)
    if not pair:
        raise ConfigError(f"Pair not found: {pair_name}")
    paribu_key, paribu_secret, binance_key, binance_secret = _resolve_api_keys(
        config, api_settings
    )
    paribu_config = replace(config.paribu, api_key=paribu_key, api_secret=paribu_secret)
    binance_config = replace(config.binance, api_key=binance_key, api_secret=binance_secret)
    paribu = ParibuClient(paribu_config)
    binance = BinanceClient(
        binance_config.futures_base_url,
        binance_config.spot_base_url,
        binance_config.api_key,
        binance_config.api_secret,
        binance_config.recv_window_ms,
    )
    return BotEngine(pair, paribu, binance, settings, logger=logger, log_callback=log_cb)


class BotApp(tk.Tk):
    def __init__(self, config_path: str, settings_path: str, logger: logging.Logger) -> None:
        super().__init__()
        self.title("Cezmi Bot")
        self.geometry("820x540")
        self._config_path = config_path
        self._settings_path = settings_path
        self._logger = logger
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._bot: BotEngine | None = None
        self._settings_store = SettingsStore(settings_path)
        self._settings = self._settings_store.load()

        self._build_ui()
        self._load_config()
        self._load_settings()
        self.after(200, self._flush_log_queue)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")

        bot_tab = ttk.Frame(notebook)
        settings_tab = ttk.Frame(notebook)
        notebook.add(bot_tab, text="Bot")
        notebook.add(settings_tab, text="Ayarlar")

        self._build_bot_tab(bot_tab)
        self._build_settings_tab(settings_tab)

    def _build_bot_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        form = ttk.Frame(parent)
        form.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Parite").grid(row=0, column=0, sticky="w")
        self.pair_var = tk.StringVar()
        self.pair_combo = ttk.Combobox(form, textvariable=self.pair_var, state="readonly")
        self.pair_combo.grid(row=0, column=1, sticky="ew")

        ttk.Label(form, text="Emir miktarı (coin)").grid(row=1, column=0, sticky="w")
        self.qty_var = tk.StringVar(value="100")
        ttk.Entry(form, textvariable=self.qty_var).grid(row=1, column=1, sticky="ew")

        ttk.Label(form, text="Kar yüzdesi").grid(row=2, column=0, sticky="w")
        self.profit_var = tk.StringVar(value="1")
        ttk.Entry(form, textvariable=self.profit_var).grid(row=2, column=1, sticky="ew")

        ttk.Label(form, text="Polling (sn)").grid(row=3, column=0, sticky="w")
        self.poll_var = tk.StringVar(value="2")
        ttk.Entry(form, textvariable=self.poll_var).grid(row=3, column=1, sticky="ew")

        ttk.Label(form, text="Leverage").grid(row=4, column=0, sticky="w")
        self.leverage_var = tk.StringVar(value="5")
        ttk.Entry(form, textvariable=self.leverage_var).grid(row=4, column=1, sticky="ew")

        ttk.Label(form, text="Pozisyon senkron (sn)").grid(row=5, column=0, sticky="w")
        self.sync_var = tk.StringVar(value="30")
        ttk.Entry(form, textvariable=self.sync_var).grid(row=5, column=1, sticky="ew")

        self.dry_run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Dry Run", variable=self.dry_run_var).grid(
            row=6, column=1, sticky="w"
        )

        button_frame = ttk.Frame(form)
        button_frame.grid(row=7, column=0, columnspan=2, pady=5)
        ttk.Button(button_frame, text="Başlat", command=self._start_bot).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Durdur", command=self._stop_bot).grid(row=0, column=1, padx=5)

        self.status_var = tk.StringVar(value="Hazır.")
        ttk.Label(form, textvariable=self.status_var).grid(row=8, column=0, columnspan=2, sticky="w")

        self.log_text = tk.Text(parent, height=16, state="disabled")
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        parent.rowconfigure(1, weight=1)

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        form = ttk.Frame(parent)
        form.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Paribu API Key").grid(row=0, column=0, sticky="w")
        self.paribu_key_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.paribu_key_var).grid(row=0, column=1, sticky="ew")

        ttk.Label(form, text="Paribu API Secret").grid(row=1, column=0, sticky="w")
        self.paribu_secret_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.paribu_secret_var, show="*").grid(
            row=1, column=1, sticky="ew"
        )

        ttk.Label(form, text="Binance API Key").grid(row=2, column=0, sticky="w")
        self.binance_key_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.binance_key_var).grid(row=2, column=1, sticky="ew")

        ttk.Label(form, text="Binance API Secret").grid(row=3, column=0, sticky="w")
        self.binance_secret_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.binance_secret_var, show="*").grid(
            row=3, column=1, sticky="ew"
        )

        save_button = ttk.Button(form, text="Kaydet", command=self._save_settings)
        save_button.grid(row=4, column=0, columnspan=2, pady=5)

    def _load_config(self) -> None:
        try:
            config = load_config(self._config_path)
        except ConfigError as exc:
            messagebox.showerror("Config Error", str(exc))
            self.destroy()
            return
        pairs = [pair.name for pair in config.pairs]
        self.pair_combo["values"] = pairs
        if pairs:
            self.pair_combo.current(0)

    def _load_settings(self) -> None:
        self.paribu_key_var.set(self._settings.get("paribu_api_key", ""))
        self.paribu_secret_var.set(self._settings.get("paribu_api_secret", ""))
        self.binance_key_var.set(self._settings.get("binance_api_key", ""))
        self.binance_secret_var.set(self._settings.get("binance_api_secret", ""))

    def _save_settings(self) -> None:
        self._settings = {
            "paribu_api_key": self.paribu_key_var.get().strip(),
            "paribu_api_secret": self.paribu_secret_var.get().strip(),
            "binance_api_key": self.binance_key_var.get().strip(),
            "binance_api_secret": self.binance_secret_var.get().strip(),
        }
        self._settings_store.save(self._settings)
        self.status_var.set("Ayarlar kaydedildi.")

    def _get_api_settings(self) -> Dict[str, str]:
        return {
            "paribu_api_key": self.paribu_key_var.get().strip(),
            "paribu_api_secret": self.paribu_secret_var.get().strip(),
            "binance_api_key": self.binance_key_var.get().strip(),
            "binance_api_secret": self.binance_secret_var.get().strip(),
        }

    def _start_bot(self) -> None:
        if self._bot:
            messagebox.showinfo("Bilgi", "Bot zaten çalışıyor.")
            return
        try:
            api_settings = self._get_api_settings()
            settings = EngineSettings(
                order_qty=Decimal(self.qty_var.get()),
                profit_percent=Decimal(self.profit_var.get()),
                poll_interval=float(self.poll_var.get()),
                leverage=int(self.leverage_var.get()),
                position_sync_interval=float(self.sync_var.get()),
                dry_run=bool(self.dry_run_var.get()),
            )
            self._bot = build_bot(
                self._config_path,
                self.pair_var.get(),
                settings,
                self._logger,
                self._log_queue.put,
                api_settings,
            )
            self._bot.start()
            self.status_var.set("Çalışıyor.")
        except Exception as exc:
            messagebox.showerror("Başlatılamadı", str(exc))
            self._bot = None

    def _stop_bot(self) -> None:
        if not self._bot:
            return
        self._bot.stop()
        self._bot = None
        self.status_var.set("Durduruldu.")

    def _flush_log_queue(self) -> None:
        while True:
            try:
                message = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
        self.after(200, self._flush_log_queue)


def run_headless(args: argparse.Namespace, logger: logging.Logger, api_settings: Dict[str, str]) -> None:
    settings = EngineSettings(
        order_qty=Decimal(args.order_qty),
        profit_percent=Decimal(args.profit_pct),
        poll_interval=float(args.poll_interval),
        leverage=int(args.leverage),
        position_sync_interval=float(args.position_sync_interval),
        dry_run=bool(args.dry_run),
    )
    bot = build_bot(args.config, args.pair, settings, logger, lambda msg: None, api_settings)
    bot.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
        bot.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Paribu/Binance hedge bot")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--settings", default=SETTINGS_PATH)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pair", default="")
    parser.add_argument("--order-qty", default="100")
    parser.add_argument("--profit-pct", default="1")
    parser.add_argument("--poll-interval", default="2")
    parser.add_argument("--leverage", default="5")
    parser.add_argument("--position-sync-interval", default="30")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logger = configure_logging()

    if args.headless:
        if not args.pair:
            raise SystemExit("--pair is required in headless mode")
        api_settings = SettingsStore(args.settings).load()
        run_headless(args, logger, api_settings)
        return

    app = BotApp(args.config, args.settings, logger)
    app.mainloop()


if __name__ == "__main__":
    main()
