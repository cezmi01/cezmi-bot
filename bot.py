# -*- coding: utf-8 -*-
"""
Multi-Exchange Çoklu Coin Çekim Botu (GUI) - OPTIMIZED
------------------------------------------------------
- Bakiye kontrolü paralel, çekim sıralı (rate limit koruması)
- Sadece bakiyesi > 0 olan coinler için çekim yapılır
- Kaynak borsa: Binance / Bybit / OKX
- config.json'dan adres/network okur
 
OKX FIX (STRICT NETWORK):
- OKX tarafında config’te network verilmişse, SADECE o network ile eşleşiyorsa çekim yapar.
- Eşleşme yoksa veya eşleşen ağ canWd=false ise çekim yapmaz (fallback yok).
"""
 
import os
import re
import json
import hmac
import time
import base64
import asyncio
import logging
import threading
import hashlib
import uuid
import socket
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from queue import Queue, Empty
from urllib.parse import urlencode
 
import tkinter as tk
from tkinter import ttk, messagebox
 
import aiohttp
from dotenv import load_dotenv
 
APP_TITLE = "Multi-Exchange Transfer Botu"
CONFIG_PATH = Path("config.json")
LOG_PATH = Path("withdraw_logs.jsonl")
 
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
 
UI_POLL_MS = 100
REQUIRE_STATIC_IP = False
WITHDRAW_DELAY = 0.3  # Çekimler arası bekleme süresi (saniye)
BALANCE_BATCH_SIZE = 10  # Bakiye kontrolü batch boyutu
BALANCE_BATCH_DELAY = 0.5  # Batch'ler arası bekleme (saniye)
MIN_BALANCE_USD = 1.0  # Minimum bakiye eşiği (USD karşılığı tahmini - toz filtresi)
 
 
def write_log(row: dict):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
 
 
def floor_amount(value: Decimal, step: str = "0.00000001") -> Decimal:
    return value.quantize(Decimal(step), rounding=ROUND_DOWN)
 
 
# ═══════════════════════════════════════════════════════════════
#                         BASE ADAPTER
# ═══════════════════════════════════════════════════════════════
class BaseExchange:
    name = "BASE"
 
    async def preflight(self):
        raise NotImplementedError
 
    async def get_balance(self, session, symbol: str) -> Decimal:
        raise NotImplementedError
 
    async def withdraw(self, session, symbol, network, address, memo, amount: Decimal):
        raise NotImplementedError

# (DEVAMINI burada senin sohbet mesajındaki tam koddan parça parça ekleyeceğim.)

