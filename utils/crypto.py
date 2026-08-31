"""utils/crypto.py — шифрование персональных данных (0.4).

Шифруются telegram_id и всё, что на него ссылается (users.telegram_id PK,
objects.created_by, insights.user_id, user_notes.user_id/admin_id), плюс
username/full_name и текст заметок админа — единственные прямые
идентификаторы человека в БД. Остальное (тексты инсайдов/объектов, credits,
даты) — рабочий контент, не персональные данные, не шифруется.

Два примитива:
- encrypt_id()/decrypt_id() — AES-SIV (RFC 5297), детерминированное AEAD:
  один и тот же telegram_id всегда даёт один и тот же шифротекст, что и
  позволяет искать/джойнить по зашифрованной колонке в SQL напрямую.
- encrypt_text()/decrypt_text() — AES-256-GCM со случайным nonce на каждый
  вызов: для полей без точечного поиска (username, full_name, заметки),
  где важнее не давать вообще никакой информации о содержимом.

Ключ (APP_SECRET_KEY) никогда не используется напрямую — проходит
HKDF-SHA256 с разными info-метками для каждой цели, а шифротекст хранит
версию ключа первым байтом (задел на ротацию без даунтайма).

APP_SECRET_KEY обязателен в обоих режимах (боевой бот и бета-бот) и должен
быть одним и тем же значением что там, что там: бета-бот при каждом
локальном запуске подтягивает снимок боевой БД как есть, не расшифровывая
(см. database/beta_sync.py) — расшифровать эти данные локально сможет
только тот же самый ключ, которым их зашифровал боевой бот.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_MIN_SECRET_BYTES = 32  # 256 бит
_GCM_NONCE_LEN = 12
_ID_BYTE_LEN = 8  # telegram_id укладывается в BIGINT/8 байт

_ENC_INFO = b"PinskUrbexBot|v1|field-aesgcm"
_IDX_INFO = b"PinskUrbexBot|v1|id-aessiv"


def _decode_secret(raw: str) -> bytes:
    """Секрет ожидается в base64 (так его печатает scripts/generate_secret_key.py
    и Render generateValue), но подойдёт и любая достаточно длинная строка."""
    raw = raw.strip()
    try:
        decoded = base64.b64decode(raw, validate=True)
        if decoded:
            return decoded
    except Exception:
        pass
    return raw.encode("utf-8")


def _load_master_secret() -> bytes:
    raw = os.getenv("APP_SECRET_KEY", "").strip()
    if not raw:
        raise RuntimeError(
            "Не найден APP_SECRET_KEY — без него бот не может шифровать/расшифровывать "
            "персональные данные в БД. Сгенерируйте ключ:\n"
            "    python -m scripts.generate_secret_key\n"
            "и вставьте результат в .env — то же значение, что и на Render "
            "(Environment → APP_SECRET_KEY), в обоих режимах (боевом и бета)."
        )

    secret = _decode_secret(raw)
    if len(secret) < _MIN_SECRET_BYTES:
        raise RuntimeError(
            f"APP_SECRET_KEY слишком короткий: {len(secret)} байт, нужно минимум "
            f"{_MIN_SECRET_BYTES} (256 бит). Сгенерируйте: python -m scripts.generate_secret_key"
        )
    return secret


def _derive(master: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(master)


class _KeySet:
    __slots__ = ("gcm", "siv")

    def __init__(self, master: bytes, version: int) -> None:
        tag = str(version).encode("ascii")
        self.gcm = AESGCM(_derive(master, _ENC_INFO + b"|" + tag, 32))
        self.siv = AESSIV(_derive(master, _IDX_INFO + b"|" + tag, 64))


def _as_bytes(data) -> bytes:
    """bytea из psycopg2 иногда приходит как memoryview — приводим к bytes."""
    return bytes(data) if not isinstance(data, bytes) else data


_CURRENT_VERSION = 1
_KEY_VERSIONS: dict[int, _KeySet] = {_CURRENT_VERSION: _KeySet(_load_master_secret(), _CURRENT_VERSION)}


def _keyset_for(version: int) -> _KeySet:
    try:
        return _KEY_VERSIONS[version]
    except KeyError:
        raise ValueError(f"Неизвестная версия ключа шифрования: {version}") from None


def encrypt_id(value: int | None) -> bytes | None:
    if value is None:
        return None
    keyset = _keyset_for(_CURRENT_VERSION)
    plaintext = int(value).to_bytes(_ID_BYTE_LEN, "big", signed=True)
    return bytes([_CURRENT_VERSION]) + keyset.siv.encrypt(plaintext, None)


def decrypt_id(data) -> int | None:
    if data is None:
        return None
    data = _as_bytes(data)
    keyset = _keyset_for(data[0])
    plaintext = keyset.siv.decrypt(data[1:], None)
    return int.from_bytes(plaintext, "big", signed=True)


def encrypt_text(value: str | None) -> bytes | None:
    if value is None:
        return None
    keyset = _keyset_for(_CURRENT_VERSION)
    nonce = os.urandom(_GCM_NONCE_LEN)
    ciphertext = keyset.gcm.encrypt(nonce, value.encode("utf-8"), None)
    return bytes([_CURRENT_VERSION]) + nonce + ciphertext


def decrypt_text(data) -> str | None:
    if data is None:
        return None
    data = _as_bytes(data)
    keyset = _keyset_for(data[0])
    nonce = data[1 : 1 + _GCM_NONCE_LEN]
    ciphertext = data[1 + _GCM_NONCE_LEN :]
    return keyset.gcm.decrypt(nonce, ciphertext, None).decode("utf-8")
