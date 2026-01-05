#!/usr/bin/env python3
"""
Myfxbook Community Outlook Alarm + Telegram Bot

- Usa API Myfxbook per prendere il sentiment
- Invia alert su Telegram se LONG% o SHORT% >= soglia
- Funziona in modalità ONE_SHOT su GitHub Actions
"""

from __future__ import annotations
import os
import json
import urllib.request
import urllib.parse
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

# --- CONFIG ---
BASE_URL = "https://www.myfxbook.com/api"
DEFAULT_THRESHOLD = 65.0

# Telegram (da GitHub Secrets)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ONE_SHOT = True su GitHub Actions
ONE_SHOT = os.environ.get("ONE_SHOT", "false").lower() == "true"

# --- DATACLASS ---
@dataclass(frozen=True)
class SentimentSnapshot:
    symbol: str
    long_pct: float
    short_pct: float

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
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram token o chat ID mancanti")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode":"HTML"}
    try:
        import requests
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print("Errore invio Telegram:", r.text)
    except Exception as e:
        print("Errore invio Telegram:", e)

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
    email = os.environ.get("MYFXBOOK_EMAIL")
    password = os.environ.get("MYFXBOOK_PASSWORD")
    if not email or not password:
        print("Imposta MYFXBOOK_EMAIL e MYFXBOOK_PASSWORD nei secrets")
        return

    client = MyfxbookClient(email, password)
    last_state: Dict[str,str] = {}

    try:
        while True:
            stamp = now_stamp()
            try:
                sentiments = client.get_outlook()
                alerts = []
                for sym, snap in sentiments.items():
                    cur = classify_state(snap)
                    prev = last_state.get(sym,"NONE")
                    last_state[sym] = cur
                    if cur != "NONE" and cur != prev:
                        alerts.append((sym,snap.long_pct,snap.short_pct,cur,prev))
                if alerts:
                    message = f"📊 <b>Myfxbook Alert</b>\nOra: {stamp}\n\n"
                    for sym,lp,sp,cur,prev in alerts:
                        reason = "ENTRY" if prev=="NONE" else f"FLIP {prev}→{cur}"
                        message += f"{sym}: long={lp:.1f}% short={sp:.1f}% → {state_action(cur)} [{reason}]\n"
                    send_telegram(message)
                else:
                    print(f"{stamp} Nessun nuovo alert")
            except Exception as e:
                print(f"{stamp} ERRORE: {e}")

            if ONE_SHOT:
                break
            time.sleep(15*60)

    finally:
        client.logout()

if __name__=="__main__":
    main()
