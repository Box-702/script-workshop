from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import db as dbm
from ..config import get_settings
from ..ids import gen_id

LOCAL_USER_ID = "local_user"


@dataclass(frozen=True)
class DecryptedModelKey:
    provider: str
    api_key: str
    base_url: str
    model: str


def _master_key() -> bytes:
    configured = get_settings().key_encryption_key.strip()
    if configured:
        try:
            decoded = base64.urlsafe_b64decode(configured + "===")
            if len(decoded) >= 32:
                return decoded[:32]
        except Exception:
            pass
        return hashlib.sha256(configured.encode("utf-8")).digest()

    # Local-only fallback. Production should set KEY_ENCRYPTION_KEY.
    return hashlib.sha256(b"script-workshop-local-dev-key").digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        counter_bytes = counter.to_bytes(4, "big")
        chunks.append(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:length]


def seal_secret(value: str) -> str:
    plaintext = value.encode("utf-8")
    nonce = secrets.token_bytes(16)
    key = _master_key()
    stream = _keystream(key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream, strict=True))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    payload = nonce + tag + ciphertext
    return base64.urlsafe_b64encode(payload).decode("ascii")


def open_secret(sealed: str) -> str:
    try:
        payload = base64.urlsafe_b64decode(sealed.encode("ascii"))
        nonce, tag, ciphertext = payload[:16], payload[16:48], payload[48:]
    except Exception as e:
        raise HTTPException(500, "stored model key is corrupted") from e

    key = _master_key()
    expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise HTTPException(500, "stored model key cannot be decrypted")

    stream = _keystream(key, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream, strict=True))
    return plaintext.decode("utf-8")


def create_model_key(
    db: Session,
    *,
    user_id: str = LOCAL_USER_ID,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
) -> dbm.UserModelKey:
    provider = provider.strip().lower() or "openai"
    api_key = api_key.strip()
    if provider != "openai":
        raise HTTPException(400, "unsupported model provider")
    if not is_plausible_api_key(api_key):
        raise HTTPException(
            400,
            "API key 看起来不是有效密钥。请粘贴完整 key，不要填写 ****1234 这类遮罩值、端口号或空值。",
        )

    existing = (
        db.query(dbm.UserModelKey)
        .filter_by(user_id=user_id, provider=provider, status="active")
        .all()
    )
    for item in existing:
        item.status = "revoked"

    key = dbm.UserModelKey(
        id=gen_id("key"),
        user_id=user_id,
        provider=provider,
        base_url=base_url.strip(),
        default_model=model.strip(),
        encrypted_api_key=seal_secret(api_key),
        key_last4=api_key[-4:],
        status="active",
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key


def is_plausible_api_key(api_key: str) -> bool:
    value = (api_key or "").strip()
    if len(value) < 8:
        return False
    if "*" in value or value.lower().startswith(("bearer ", "http://", "https://")):
        return False
    return True


def list_model_keys(db: Session, *, user_id: str = LOCAL_USER_ID) -> list[dbm.UserModelKey]:
    return (
        db.query(dbm.UserModelKey)
        .filter_by(user_id=user_id)
        .order_by(dbm.UserModelKey.created_at.desc())
        .all()
    )


def revoke_model_key(db: Session, key_id: str, *, user_id: str = LOCAL_USER_ID) -> None:
    key = db.get(dbm.UserModelKey, key_id)
    if not key or key.user_id != user_id:
        raise HTTPException(404, "model key not found")
    key.status = "revoked"
    db.commit()


def get_active_model_key(
    db: Session, *, user_id: str = LOCAL_USER_ID, provider: str = "openai"
) -> dbm.UserModelKey | None:
    return (
        db.query(dbm.UserModelKey)
        .filter_by(user_id=user_id, provider=provider, status="active")
        .order_by(dbm.UserModelKey.created_at.desc())
        .first()
    )


def decrypt_model_key(key: dbm.UserModelKey) -> DecryptedModelKey:
    return DecryptedModelKey(
        provider=key.provider,
        api_key=open_secret(key.encrypted_api_key),
        base_url=key.base_url,
        model=key.default_model,
    )
