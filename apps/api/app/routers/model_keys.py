"""User model key endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from .. import db as dbm
from ..schemas import ModelKeyCreate, ModelKeyOut, ModelKeyTestResponse
from ..services.model_keys import (
    create_model_key,
    decrypt_model_key,
    get_active_model_key,
    is_plausible_api_key,
    list_model_keys,
    revoke_model_key,
)
from .deps import CurrentUser, DbSession

router = APIRouter(prefix="/api", tags=["model-keys"])


def _key_out(key: dbm.UserModelKey) -> ModelKeyOut:
    return ModelKeyOut(
        id=key.id,
        provider=key.provider,
        base_url=key.base_url,
        default_model=key.default_model,
        key_last4=key.key_last4,
        status=key.status,
        created_at=key.created_at.isoformat(),
        updated_at=key.updated_at.isoformat(),
    )


@router.get("/user/model-keys", response_model=list[ModelKeyOut])
def get_model_keys(db: DbSession, current_user: CurrentUser) -> list[ModelKeyOut]:
    return [_key_out(key) for key in list_model_keys(db, user_id=current_user.id)]


@router.post("/user/model-keys", response_model=ModelKeyOut)
def save_model_key(
    payload: ModelKeyCreate, db: DbSession, current_user: CurrentUser
) -> ModelKeyOut:
    key = create_model_key(
        db,
        user_id=current_user.id,
        provider=payload.provider,
        api_key=payload.api_key,
        base_url=payload.base_url,
        model=payload.model,
    )
    return _key_out(key)


@router.get("/user/model-keys/active", response_model=ModelKeyOut | None)
def get_active_key(db: DbSession, current_user: CurrentUser) -> ModelKeyOut | None:
    key = get_active_model_key(db, user_id=current_user.id)
    return _key_out(key) if key else None


@router.delete("/user/model-keys/{key_id}", response_model=ModelKeyTestResponse)
def delete_model_key(
    key_id: str, db: DbSession, current_user: CurrentUser
) -> ModelKeyTestResponse:
    revoke_model_key(db, key_id, user_id=current_user.id)
    return ModelKeyTestResponse(ok=True, message="model key revoked")


@router.post("/user/model-keys/{key_id}/test", response_model=ModelKeyTestResponse)
def test_model_key(
    key_id: str, db: DbSession, current_user: CurrentUser
) -> ModelKeyTestResponse:
    key = db.get(dbm.UserModelKey, key_id)
    if not key or key.user_id != current_user.id or key.status != "active":
        return ModelKeyTestResponse(ok=False, message="model key not found")
    decrypted = decrypt_model_key(key)
    if not is_plausible_api_key(decrypted.api_key):
        return ModelKeyTestResponse(ok=False, message="API key 看起来不是有效密钥")
    return ModelKeyTestResponse(
        ok=True,
        message="API key 已保存且格式可用；服务商认证会在生成时检查。",
    )
