"""模型适配配置接口（M02-02）：密钥只以环境变量引用形式出现。"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_permission, verify_csrf
from app.core.errors import ApiError, ok
from app.models import ModelConfig
from app.services import models as model_service

router = APIRouter()


class _Strict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


Provider = Literal["OPENAI_COMPATIBLE", "LOCAL_HTTP", "MOCK"]


class ModelCreate(_Strict):
    name: str = Field(min_length=1, max_length=80)
    provider: Provider
    base_url: str = Field(default="", max_length=255)
    model_name: str = Field(default="", max_length=120)
    api_key_ref: str = Field(default="", max_length=80)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=1024, gt=0, le=32000)


class ModelUpdate(_Strict):
    base_url: str | None = Field(default=None, max_length=255)
    model_name: str | None = Field(default=None, max_length=120)
    api_key_ref: str | None = Field(default=None, max_length=80)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0, le=32000)
    status: Literal["ACTIVE", "DISABLED"] | None = None


def _get(session: Session, model_id: int) -> ModelConfig:
    config = session.get(ModelConfig, model_id)
    if config is None:
        raise ApiError(404, "MODEL_NOT_FOUND", "模型配置不存在")
    return config


@router.post("/models", status_code=201)
async def create_model(
    payload: ModelCreate,
    current: CurrentUser = Depends(require_permission("platform:model:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    config = model_service.create(
        session,
        name=payload.name,
        provider=payload.provider,
        base_url=payload.base_url,
        model_name=payload.model_name,
        api_key_ref=payload.api_key_ref,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    return ok(model_service.serialize(config), "模型配置创建成功")


@router.get("/models")
async def list_models(
    current: CurrentUser = Depends(require_permission("platform:model:manage")),
    session: Session = Depends(get_db),
) -> dict:
    rows = session.execute(select(ModelConfig).order_by(ModelConfig.id)).scalars().all()
    return ok({"items": [model_service.serialize(row) for row in rows], "total": len(rows)}, "模型配置列表")


@router.get("/models/{model_id}")
async def get_model(
    model_id: int,
    current: CurrentUser = Depends(require_permission("platform:model:manage")),
    session: Session = Depends(get_db),
) -> dict:
    return ok(model_service.serialize(_get(session, model_id)), "模型配置详情")


@router.patch("/models/{model_id}")
async def update_model(
    model_id: int,
    payload: ModelUpdate,
    current: CurrentUser = Depends(require_permission("platform:model:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    config = _get(session, model_id)
    updated = model_service.update(session, config, **payload.model_dump(exclude_none=True))
    return ok(model_service.serialize(updated), "模型配置已更新")


@router.post("/models/{model_id}/test")
async def test_model(
    model_id: int,
    current: CurrentUser = Depends(require_permission("platform:model:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    config = _get(session, model_id)
    result = model_service.test_connectivity(config)
    return ok(result, "连接测试完成" if result["ok"] else "连接测试失败")