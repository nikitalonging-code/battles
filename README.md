# NFT Battle Bot

Мини-апп для батлов на NFT-подарки Telegram. Кубик решает, кто забирает подарки.

## Как это работает

1. Игрок отправляет NFT-подарок на **аккаунт-банк** (`BANK_USERNAME`).
2. Бот раз в N секунд синкает подарки банка и зачисляет их в **инвентарь** отправителя (по `sender_user`).
3. В мини-аппе игрок создаёт / вступает в битву, выбирая подарок **из инвентаря** (Business у игрока не нужен).
4. Когда слоты заполнены — кубики в канале результатов, победитель забирает подарки проигравших (`transferGift` с банка).
5. В инвентаре можно **Вывести** подарок обратно на свой Telegram-аккаунт.

## Установка

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполнить переменные
python main.py
```

Нужен HTTPS для WebApp (`WEBAPP_URL`).

### .env

```env
BOT_TOKEN=
RESULTS_CHANNEL=@channel
WEBAPP_URL=https://your-domain.com
BANK_BUSINESS_CONNECTION_ID=   # см. ниже
BANK_USERNAME=giftbank
BANK_SYNC_INTERVAL=20
```

### Как получить BANK_BUSINESS_CONNECTION_ID

1. На аккаунте-банке: Настройки → Telegram Business → Чат-боты → подключить этого бота.
2. Права: «Просмотр подарков и звёзд» + «Передача и апгрейд подарков».
3. В консоли бота появится:
   `>>> BUSINESS CONNECTION ID: ...`
4. Вставить в `.env` и перезапустить.

Канал результатов — публичный, бот админ с правом писать.
