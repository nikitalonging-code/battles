import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from app.config import settings


class InitDataError(Exception):
    pass


def validate_init_data(init_data: str, max_age_seconds: int = 3600) -> dict:
    """Проверяет подпись initData, которую мини-апп получает от Telegram.WebApp,
    и возвращает распарсенные данные (включая user). Кидает InitDataError, если подпись неверна."""
    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash отсутствует")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataError("Неверная подпись initData")

    auth_date = int(parsed.get("auth_date", 0))
    import time

    if time.time() - auth_date > max_age_seconds:
        raise InitDataError("initData устарела")

    if "user" in parsed:
        parsed["user"] = json.loads(parsed["user"])

    return parsed
