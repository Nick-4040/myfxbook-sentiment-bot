import requests
import os
from datetime import datetime


MYFXBOOK_URL = "https://www.myfxbook.com/api/get-community-outlook.json"
THRESHOLD = 65

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


print("TOKEN presente:", TELEGRAM_TOKEN is not None)
print("CHAT ID:", CHAT_ID)


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": msg
    })

def main():
    r = requests.get(MYFXBOOK_URL, timeout=10)
    data = r.json()

    pair = "EURUSD"  # per ora fisso, poi lo renderemo dinamico

    if pair not in data:
        return

    long_p = data[pair]["longPercentage"]
    short_p = data[pair]["shortPercentage"]

    if long_p >= THRESHOLD or short_p >= THRESHOLD:
        direction = "BUY" if long_p >= THRESHOLD else "SELL"
        value = long_p if direction == "BUY" else short_p

        msg = (
            f"{pair}\n"
            f"{direction} {value:.1f}%\n"
            f"{datetime.utcnow().strftime('%H:%M UTC')}"
        )
        send_telegram(msg)

if __name__ == "__main__":
    main()
