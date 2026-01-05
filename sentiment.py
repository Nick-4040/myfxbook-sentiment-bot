#!/usr/bin/env python3
"""
Bot Myfxbook Community Outlook + Telegram

Funzionalità:
- Legge il sentiment da Myfxbook
- Invia alert per pair sopra soglia
- Bot Telegram interattivo con comandi:
  /pairs  - lista pair disponibili con bandiere
  /add    - aggiunge pair alla lista dell'utente
  /remove - rimuove pair dalla lista
  /mylist - mostra pair dell'utente
"""

from __future__ import annotations
import os
import sys
import time
import json
import getpass
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests

# -------------------- CONFIG --------------------
DEFAULT_THRESHOLD = 65.0
BASE_URL = "https://www.myfxbook.com/api"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MYFXBOOK_EMAIL = os.environ.get("MYFXBOOK_EMAIL")
MYFXBOOK_PASSWORD = os.environ.get("MYFXBOOK_PASSWORD")
ONE_SHOT = os.environ.get("ONE_SHOT", "true").lower() == "true"

# utenti -> dict chat_id: [pair1, pair2, ...]
USER_PAIRS: Dict[int, List[str]] = {}

# lista pair disponibili e bandiere
PAIR_FLAGS = {
    "EURUSD": "🇪🇺🇺🇸",
    "GBPUSD": "🇬🇧🇺🇸",
    "USDJPY": "🇺🇸🇯🇵",
    "AUDUSD": "🇦🇺🇺🇸",
    "USDCAD": "🇺🇸🇨🇦",
    "USDCHF": "🇺🇸🇨🇭",
    "NZDUSD": "🇳🇿🇺🇸",
}

# -------------------- DATACLASS --------------------
@dataclass(frozen=True)
class SentimentSnapshot:
    symbol: str
    long_pct: float
    short_pct: float

# -------------------- MYFXBOOK CLIENT --------------------
class MyfxbookClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session_id: Optional[str] = None

    def login(self) -> str:
        url = f"{BASE_URL}/login.json?email={urllib.parse.quote(self.email)}&password={urllib.parse.quote(self.password)}"
        payload = self._get_json(url)
        if payload.get("error"):
            raise Exception(f"Myfxbook login error: {payload.get('message')}")
        session = payload.get("session")
        if not session:
            raise Exception("Empty session returned")
        self.session_id = session
        return session

    def get_outlook(self) -> Dict[str, SentimentSnapshot]:
        if not self.session_id:
            self.login()
        url = f"{BASE_URL}/get-community-outlook.json?session={urllib.parse.quote(self.session_id)}"
        payload = self._get_json(url)
        symbols = payload.get("symbols", [])
        out = {}
        for item in symbols:
            symbol = item.get("symbol")
            long_pct = float(item.get("longPercentage", 0))
            short_pct = float(item.get("shortPercentage", 0))
            out[symbol.upper()] = SentimentSnapshot(symbol.upper(), long_pct, short_pct)
        return out

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "python-requests"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

# -------------------- TELEGRAM UTILS --------------------
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    resp = requests.post(url, data=data)
    if not resp.ok:
        print(f"Errore invio Telegram: {resp.text}")

def get_updates(offset=None):
    url = f"{TELEGRAM_API}/getUpdates"
    params = {"timeout": 5, "offset": offset}
    resp = requests.get(url, params=params)
    return resp.json()

# -------------------- COMANDI TELEGRAM --------------------
def handle_command(chat_id: int, text: str):
    text = text.strip()
    if text.startswith("/pairs"):
        msg = "\n".join(f"{p} {PAIR_FLAGS.get(p,'')}" for p in PAIR_FLAGS)
        send_message(chat_id, msg)
    elif text.startswith("/add"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "Usa /add PAIR, es: /add EURUSD")
            return
        pair = parts[1].upper()
        if pair not in PAIR_FLAGS:
            send_message(chat_id, f"Pair non valido: {pair}")
            return
        USER_PAIRS.setdefault(chat_id, [])
        if pair not in USER_PAIRS[chat_id]:
            USER_PAIRS[chat_id].append(pair)
        send_message(chat_id, f"Aggiunto {pair}")
    elif text.startswith("/remove"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "Usa /remove PAIR, es: /remove EURUSD")
            return
        pair = parts[1].upper()
        USER_PAIRS.setdefault(chat_id, [])
        if pair in USER_PAIRS[chat_id]:
            USER_PAIRS[chat_id].remove(pair)
            send_message(chat_id, f"Rimosso {pair}")
        else:
            send_message(chat_id, f"{pair} non presente nella tua lista")
    elif text.startswith("/mylist"):
        pairs = USER_PAIRS.get(chat_id, [])
        if not pairs:
            send_message(chat_id, "La tua lista è vuota")
        else:
            msg = "\n".join(f"{p} {PAIR_FLAGS.get(p,'')}" for p in pairs)
            send_message(chat_id, msg)
    else:
        send_message(chat_id, "Usa /pairs, /add, /remove, /mylist")

# -------------------- LOGICA ALERT --------------------
def classify_state(s: SentimentSnapshot, threshold: float) -> str:
    if s.long_pct >= threshold and s.short_pct >= threshold:
        return "BOTH"
    if s.long_pct >= threshold:
        return "LONG"
    if s.short_pct >= threshold:
        return "SHORT"
    return "NONE"

def state_action(state: str) -> str:
    return {"LONG":"SELL (crowded LONG)","SHORT":"BUY (crowded SHORT)","BOTH":"CHECK (both sides >= threshold)","NONE":""}.get(state,"")

# -------------------- MAIN --------------------
def main():
    print("Bot Myfxbook + Telegram")

    # 1) Poll messaggi Telegram
    last_update_id = None
    updates = get_updates()
    for u in updates.get("result", []):
        update_id = u["update_id"]
        if last_update_id and update_id <= last_update_id:
            continue
        last_update_id = update_id
        msg = u.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "")
        if chat_id and text:
            handle_command(chat_id, text)

    # 2) Controllo sentiment Myfxbook
    client = MyfxbookClient(MYFXBOOK_EMAIL, MYFXBOOK_PASSWORD)
    try:
        sentiments = client.get_outlook()
    except Exception as e:
        print(f"Errore Myfxbook: {e}")
        return

    # 3) Invia alert agli utenti
    threshold = DEFAULT_THRESHOLD
    for chat_id, pairs in USER_PAIRS.items():
        for pair in pairs:
            s = sentiments.get(pair)
            if not s:
                continue
            state = classify_state(s, threshold)
            if state != "NONE":
                msg = f"ALERT {pair}: {s.long_pct:.1f}% long / {s.short_pct:.1f}% short -> {state_action(state)}"
                send_message(chat_id, msg)

if __name__ == "__main__":
    main()
