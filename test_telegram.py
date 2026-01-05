import requests
import os

TOKEN = os.getenv("8365209009:AAHGH80VkAO0u_ro54m2SpfsxsMe2Ls2vFs")
CHAT_ID = os.getenv("263249303")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
requests.post(url, json={
    "chat_id": CHAT_ID,
    "text": "✅ Bot Telegram collegato correttamente!"
})
