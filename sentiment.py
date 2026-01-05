import requests
import json
import os
from datetime import datetime

# URL Myfxbook
MYFXBOOK_URL = "https://www.myfxbook.com/api/get-community-outlook.json"
THRESHOLD = 65

# Prendere i secrets da GitHub Actions
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Funzioni per leggere i pair
def load_pairs():
    try:
        with open("pairs.json", "r") as f:
            return json.load(f).get("pairs", [])
    except Exception as e:
        print("Errore nel leggere pairs.json:", e)
        return []

# Funzione per inviare messaggio Telegram
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    })
    print("Telegram response:", r.text)  # utile per debug GitHub

# Funzione principale
def check_sentiment():
    try:
        r = requests.get(MYFXBOOK_URL, timeout=10)
        data = r.json()
    except Exception as e:
        print("Errore nel leggere Myfxbook:", e)
        return

    pairs = load_pairs()
    if not pairs:
        print("Nessun pair da controllare.")
        return

    for pair in pairs:
        if pair not in data:
            print(f"Pair {pair} non trovato in Myfxbook")
            continue

        long_p = data[pair].get("longPercentage", 0)
        short_p = data[pair].get("shortPercentage", 0)

        # Alert solo se supera la soglia
        if long_p >= THRESHOLD or short_p >= THRESHOLD:
            direction = "BUY" if long_p >= THRESHOLD else "SELL"
            value = long_p if direction == "BUY" else short_p

            msg = (
                f"📊 <b>{pair}</b>\n"
                f"Direzione: <b>{direction}</b>\n"
                f"Sentiment: <b>{value:.1f}%</b>\n"
                f"Ora: {datetime.utcnow().strftime('%H:%M UTC')}"
            )
            send_telegram(msg)

if __name__ == "__main__":
    check_sentiment()
