#!/usr/bin/env python3
"""
Myfxbook Community Outlook Alarm + Multi-utente Telegram Bot con selezione pair
"""

from __future__ import annotations
import os
import json
import time
import urllib.request
import urllib.parse
import requests
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

# --- CONFIG ---
BASE_URL = "https://www.myfxbook.com/api"
DEFAULT_THRESHOLD = 65.0
CHAT_DB_FILE = "users.json"  # Salva {chat_id: [pair1,pair2,...]}

# Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
URL_TELEGRAM = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

ONE_SHOT = os.environ.get("ONE_SHOT", "false").lower() == "true"

# Myfxbook credentials
MYFXBOOK_EMAIL = os.environ.get("MYFXBOOK_EMAIL")
MYFXBOOK_PASSWORD = os.environ.get("MYFXBOOK_PASSWORD")

# --- DATACLASS ---
@dataclass(frozen=True)
class SentimentSnapshot:
    symbol: str
    long_pct: float
    short_pct: float

# --- MAPPA BANDIERE ---
CURRENCY_FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧",
    "JPY": "🇯🇵", "CHF": "🇨🇭", "AUD": "🇦🇺",
    "CAD": "🇨🇦", "NZD": "🇳🇿"
}

def pair_flags(pair):
    if len(pair) != 6:
        return ""
    return CURRENCY_FLAGS.get(pair[:3], "") + CURRENCY_FLAGS.get(pair[3:], "")

# --- MYFXBOOK CLIENT ---
class MyfxbookClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session_id: Optional[str] = None

    def login(self):
        url = f"{BASE_URL}/login.json?email={urllib.parse.quote(self.email)}&password={urllib.parse.quote(self.password)}"
        payload = self._get_json(url)
        if payload.get("error"):
            raise Exception("Login failed: " + str(payload.get("message")))
        self.session_id = urllib.parse.unquote(payload.get("session"))

    def logout(self):
        if self.session_id:
            url = f"{BASE_URL}/logout.json?session={urllib.parse.quote(self.session_id)}"
            try: self._get_json(url)
            except: pass
            self.session_id = None

    def get_outlook(self) -> Dict[str, SentimentSnapshot]:
        if not self.session_id:
            self.login()
        url = f"{BASE_URL}/get-community-outlook.json?session={urllib.parse.quote(self.session_id)}"
        payload = self._get_json(url)
        result: Dict[str, SentimentSnapshot] = {}
        for item in payload.get("symbols", []):
            try:
                symbol = str(item.get("symbol") or item.get("name")).upper()
                long_pct = float(str(item.get("longPercentage")).replace("%",""))
                short_pct = float(str(item.get("shortPercentage")).replace("%",""))
                result[symbol] = SentimentSnapshot(symbol=symbol, long_pct=long_pct, short_pct=short_pct)
            except: continue
        return result

    def _get_json(self, url):
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body or "{}")

# --- TELEGRAM ---
def load_users():
    if os.path.exists(CHAT_DB_FILE):
        with open(CHAT_DB_FILE,"r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(CHAT_DB_FILE,"w") as f:
        json.dump(users,f)

def get_updates(offset=None):
    params = {"timeout": 30}
    if offset: params["offset"] = offset
    url = f"{URL_TELEGRAM}/getUpdates?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=35) as resp:
        return json.load(resp)

def send_message(chat_id, text):
    url = f"{URL_TELEGRAM}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode":"HTML"}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as resp:
            return resp.read()
    except Exception as e:
        print("Errore invio Telegram:", e)


def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 10, "offset": offset}
    resp = requests.get(url, params=params)
    return resp.json()

# Ciclo per leggere i messaggi
last_update_id = None
updates = get_updates()
for u in updates.get("result", []):
    update_id = u["update_id"]
    if last_update_id and update_id <= last_update_id:
        continue
    text = u["message"]["text"]
    chat_id = u["message"]["chat"]["id"]
    # parsing comandi qui
    if text.startswith("/pairs"):
        send_pairs(chat_id)
    elif text.startswith("/add"):
        param = text.split(" ")[1]
        add_pair(chat_id, param)
    # ...
    last_update_id = update_id + 1


# --- UTILS ---
def classify_state(s: SentimentSnapshot, threshold=DEFAULT_THRESHOLD):
    long_ok = s.long_pct >= threshold
    short_ok = s.short_pct >= threshold
    if long_ok and short_ok: return "BOTH"
    if long_ok: return "LONG"
    if short_ok: return "SHORT"
    return "NONE"

def state_action(state: str):
    return {"LONG":"SELL (crowded LONG)","SHORT":"BUY (crowded SHORT)","BOTH":"CHECK (both sides >= threshold)","NONE":""}.get(state,"")

def now_stamp():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

# --- MAIN ---
def main():
    if not TELEGRAM_TOKEN or not MYFXBOOK_EMAIL or not MYFXBOOK_PASSWORD:
        print("Imposta TELEGRAM_TOKEN, MYFXBOOK_EMAIL, MYFXBOOK_PASSWORD")
        return

    users = load_users()  # dict chat_id -> [pair,...]
    client = MyfxbookClient(MYFXBOOK_EMAIL, MYFXBOOK_PASSWORD)
    last_state: Dict[str,str] = {}
    last_update_id = None

    try:
        while True:
            stamp = now_stamp()
            # --- Legge messaggi Telegram ---
            try:
                updates = get_updates(last_update_id)
                for u in updates.get("result", []):
                    last_update_id = u["update_id"] + 1
                    chat_id = str(u["message"]["chat"]["id"])
                    text = u["message"]["text"].strip()

                    if chat_id not in users:
                        users[chat_id] = []

                    # Comandi
                    if text.startswith("/"):
                        parts = text.split()
                        cmd = parts[0].lower()
                        arg = parts[1].upper() if len(parts)>1 else None

                        if cmd=="/start":
                            send_message(chat_id, "Benvenuto! Usa /pairs per vedere tutti i pair disponibili.")
                        elif cmd=="/pairs":
                            try:
                                sentiments = client.get_outlook()
                                msg = "Tutti i pair disponibili:\n"
                                for p in sentiments.keys():
                                    msg += f"{p} {pair_flags(p)}\n"
                                send_message(chat_id, msg)
                            except: send_message(chat_id, "Errore lettura pair Myfxbook")
                        elif cmd=="/add" and arg:
                            if arg not in users[chat_id]:
                                users[chat_id].append(arg)
                                save_users(users)
                                send_message(chat_id, f"{arg} aggiunto {pair_flags(arg)}")
                        elif cmd=="/remove" and arg:
                            if arg in users[chat_id]:
                                users[chat_id].remove(arg)
                                save_users(users)
                                send_message(chat_id, f"{arg} rimosso {pair_flags(arg)}")
                        elif cmd=="/mylist":
                            msg = "I tuoi pair monitorati:\n" + "\n".join([f"{p} {pair_flags(p)}" for p in users.get(chat_id,[])])
                            send_message(chat_id, msg)
                        continue
                    # Risposta generica
                    send_message(chat_id, f"Hai scritto: {text}\nUsa /pairs, /add, /remove, /mylist")
            except Exception as e:
                print(f"{stamp} Telegram fetch error: {e}")

            # --- Legge sentiment Myfxbook ---
            try:
                sentiments = client.get_outlook()
                for uid, user_pairs in users.items():
                    msg = ""
                    for sym, snap in sentiments.items():
                        if sym not in user_pairs: continue
                        state = classify_state(snap)
                        prev = last_state.get(f"{uid}_{sym}", "NONE")
                        last_state[f"{uid}_{sym}"] = state
                        if state != "NONE" and state != prev:
                            msg += f"{sym} {pair_flags(sym)}: long={snap.long_pct}% short={snap.short_pct}% → {state_action(state)}\n"
                    if msg:
                        send_message(uid, f"📊 <b>Myfxbook Alert</b>\n{stamp}\n\n{msg}")
                print(f"{stamp} Check completato")
            except Exception as e:
                print(f"{stamp} Myfxbook error: {e}")

            if ONE_SHOT:
                break
            time.sleep(15*60)
    finally:
        client.logout()

if __name__=="__main__":
    main()
