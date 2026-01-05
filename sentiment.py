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

# Variabile per eseguire un solo ciclo su GitHub Actions
ONE_SHOT = os.environ.get("ONE_SHOT", "false").lower() == "true"

# Soglia percentuale per alert
THRESHOLD = 65.0

# Intervallo in secondi tra controlli (utile in locale)
INTERVAL_SECONDS = 15 * 60

# URL della pagina Myfxbook Community Outlook
MYFXBOOK_URL = "https://www.myfxbook.com/community/outlook"


def fetch_sentiment():
    """Scarica e restituisce i dati sentiment come dict {pair: {"long": float, "short": float}}"""
    try:
        r = requests.get(MYFXBOOK_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        html = r.text
    except Exception as e:
        print("Errore fetch pagina:", e)
        return {}

    # Cerca JSON dei dati community
    match = re.search(r"var communityData = (\{.*\});", html)
    if not match:
        print("Errore: impossibile trovare i dati sentiment nella pagina")
        return {}

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print("Errore parsing JSON:", e)
        return {}

    result = {}
    for pair, values in data.items():
        try:
            result[pair] = {
                "long": float(values["longPercentage"]),
                "short": float(values["shortPercentage"]),
            }
        except (KeyError, ValueError):
            continue
    return result


def send_telegram_message(message: str):
    """Invia messaggio Telegram usando bot"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram token o chat ID mancanti")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print("Errore invio Telegram:", r.text)
    except Exception as e:
        print("Errore invio Telegram:", e)


def classify_state(long_pct, short_pct, threshold=THRESHOLD):
    """Restituisce LONG, SHORT, BOTH o NONE"""
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
            if not sentiments:
                print(f"{stamp} Nessun dato trovato")
                if ONE_SHOT:
                    break
                time.sleep(INTERVAL_SECONDS)
                continue

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
                    reason = "ENTRY" if prev == "NONE" else f"FLIP {prev}→{cur}"
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

        if ONE_SHOT:
            break  # esce subito dopo un ciclo
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
