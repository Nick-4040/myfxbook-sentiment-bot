#!/usr/bin/env python3
import requests
import re
import json
import time
from datetime import datetime
import os

# Telegram bot token e chat ID dai GitHub Secrets
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Soglia percentuale per alert
THRESHOLD = 65.0

# Coppie da monitorare
PAIRS = ["EURUSD", "GBPUSD", "USDJPY"]  # puoi aggiungere altre

# Intervallo in secondi tra controlli (es. 15 minuti)
INTERVAL_SECONDS = 15 * 60

# URL della pagina Myfxbook Community Outlook
MYFXBOOK_URL = "https://www.myfxbook.com/community/outlook"


def fetch_sentiment():
    """Scarica e restituisce i dati sentiment come dict {pair: {"long": float, "short": float}}"""
    r = requests.get(MYFXBOOK_URL, headers={"User-Agent": "Mozilla/5.0"})
    html = r.text

    # Cerca JSON dei dati community
    match = re.search(r"var communityData = (\{.*\});", html)
    if not match:
        print("Errore: impossibile trovare i dati sentiment nella pagina")
        return {}

    data = json.loads(match.group(1))
    result = {}
    for pair in PAIRS:
        if pair in data:
            result[pair] = {
                "long": float(data[pair]["longPercentage"]),
                "short": float(data[pair]["shortPercentage"]),
            }
        else:
            print(f"Pair {pair} non trovato nella pagina Myfxbook")
    return result


def send_telegram_message(message: str):
    """Invia messaggio Telegram usando bot"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print("Errore invio Telegram:", r.text)
    except Exception as e:
        print("Errore invio Telegram:", e)


def classify_state(long_pct, short_pct, threshold=THRESHOLD):
    """Restituisce LONG, SHORT o NONE"""
    if long_pct >= threshold and short_pct >= threshold:
        return "BOTH"
    elif long_pct >= threshold:
        return "LONG"
    elif short_pct >= threshold:
        return "SHORT"
    else:
        return "NONE"


def main():
    last_state = {}  # tiene traccia dello stato precedente per ogni pair

    while True:
        stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        try:
            sentiments = fetch_sentiment()
            alerts = []

            for pair, values in sentiments.items():
                long_pct = values["long"]
                short_pct = values["short"]
                state = classify_state(long_pct, short_pct)
                prev = last_state.get(pair, "NONE")
                last_state[pair] = state

                # alert solo se entra nella soglia o cambia lato
                if state != "NONE" and state != prev:
                    alerts.append((pair, long_pct, short_pct, state, prev))

            if alerts:
                message = f"📊 <b>Myfxbook Alert</b>\nOra: {stamp}\n\n"
                for pair, lp, sp, cur, prev in alerts:
                    if prev == "NONE":
                        reason = "ENTRY"
                    else:
                        reason = f"FLIP {prev}→{cur}"
                    action = ""
                    if cur == "LONG":
                        action = "SELL (crowded LONG)"
                    elif cur == "SHORT":
                        action = "BUY (crowded SHORT)"
                    elif cur == "BOTH":
                        action = "CHECK (both sides >= threshold)"
                    message += f"{pair}: long={lp:.1f}% short={sp:.1f}% → {action} [{reason}]\n"
                send_telegram_message(message)
            else:
                print(f"{stamp} Nessun nuovo alert")

        except Exception as e:
            print(f"{stamp} ERRORE: {e}")

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
