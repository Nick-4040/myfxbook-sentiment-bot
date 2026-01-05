import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
requests.post(url, json={
    "chat_id": CHAT_ID,
    "text": "✅ Bot Telegram collegato correttamente!"
})
