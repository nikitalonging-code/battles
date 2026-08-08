"""
Один раз локально: получить StringSession для аккаунта-банка.

1. https://my.telegram.org → API development tools → api_id + api_hash
2. pip install telethon
3. python scripts/make_session.py
4. Ввести телефон, код, 2FA если есть
5. Скопировать строку сессии в BANK_SESSION на Render
"""
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("API_ID: ").strip())
api_hash = input("API_HASH: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\n=== BANK_SESSION (скопируй целиком) ===\n")
    print(client.session.save())
    print("\n========================================\n")
