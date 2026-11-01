"""应用生命周期服务：草稿 → 测试 → 发布快照 → 停用（docs/05 §1）。"""

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import AIApplication, ApplicationVersion, ModelConfig

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")
DEFAULT_CONFIG: dict[str, Any] = {
    "model_config_id": None,
    "system_prompt": "",
    "temperature": 0.2,
    "max_tokens": 1024,
    "kb_ids": [],
    "tool_ids": [],
    "write_confirmation": True,
}


def validate_slug(slug: str) -> str:
    value = (slug or "").strip().lower()
    if not SLUG_PATTERN.match(value):
        raise ApiError(
            400,
            "INVALID_REQUEST",
            "slug 仅允许小写字母/数字/连字符，2-60 位，且不得以连字符开头或结尾",
        )
    return value


def normalize_config(raw: dict | None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    config.update(raw or {})
    config["kb_ids"] = sorted({int(item) for item in config.get("kb_ids") or []})
    config["tool_ids"] = sorted({int(item) for item in config.get("tool_ids") or []})
    config["temperature"] = float(config.get("temperature", 0.2))
    config["max_tokens"] = int(config.get("max_tokens", 1024))
    config["write_confirmation"] = bool(config.get("write_confirmation", True))
    return config


def validate_for_publish(session: Session, app: AIApplication) -> list[str]:
    """发布前校验：模型可用、系统提示词非空、绑定资源存在（docs/05 §1）。"""
    config = normalize_config(app.draft_config)
    problems: list[str] = []

    model_id = config.get("model_config_id")
    if not model_id:
        problems.append("MODEL_REQUIRED")
    else:
        model = session.get(ModelConfig, int(model_id))
        if model is None:
            problems.append("MODEL_NOT_FOUND")
        elif model.status != "ACTIVE":
            problems.append("MODEL_DISABLED")

    if not str(config.get("system_prompt") or "").strip():
        problems.append("SYSTEM_PROMPT_REQUIRED")

    if not (0 <= config["temperature"] <= 2):
        problems.append("TEMPERATURE_OUT_OF_RANGE")
    if not (1 <= config["max_tokens"] <= 32000):
        problems.append("MAX_TOKENS_OUT_OF_RANGE")

    return problems


def create_application(
    session: Session,
    *,
    name: str,
    slug: str,
    description: str | None,
    config: dict | None,
    created_by: int | None,
) -> AIApplication:
    slug_value = validate_slug(slug)
    if session.execute(select(AIApplication).where(AIApplication.name == name)).scalar_one_or_none():
        raise ApiError(409, "APPLICATION_NAME_TAKEN", "应用名称已存在")
    if session.execute(select(AIApplication).where(AIApplication.slug == slug_value)).scalar_one_or_none():
        raise ApiError(409, "SLUG_TAKEN", "slug 已被占用")

    app = AIApplication(
        name=name,
        slug=slug_value,
        description=description,
        status="DRAFT",
        draft_config=normalize_config(config),
        created_by=created_by,
    )
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def update_draft(session: Session, app: AIApplication, **fields) -> AIApplication:
    if app.status == "DISABLED":
        raise ApiError(422, "APPLICATION_DISABLED", "已停用应用不可编辑")
    if "config" in fields and fields["config"] is not None:
        app.draft_config = normalize_config({**(app.draft_config or {}), **fields["config"]})
    for key in ("name", "description"):
        value = fields.get(key)
        if value is not None:
            setattr(app, key, value)
    if fields.get("slug"):
        new_slug = validate_slug(fields["slug"])
        other = session.execute(
            select(AIApplication).where(AIApplication.slug == new_slug)
        ).scalar_one_or_none()
        if other is not None and other.id != app.id:
            raise ApiError(409, "SLUG_TAKEN", "slug 已被占用")
        app.slug = new_slug
    session.commit()
    session.refresh(app)
    return app


def run_draft_test(session: Session, app: AIApplication, message: str, transport=None) -> dict[str, Any]:
    """草稿测试：校验配置并给出可验证的离线回显，不写会话、不调用写工具。"""
    problems = validate_for_publish(session, app)
    config = normalize_config(app.draft_config)
    model = session.get(ModelConfig, int(config["model_config_id"])) if config.get("model_config_id") else None

    echo = (
        f"[draft-test] {app.name} 收到：{message}\n"
        f"system_prompt 长度={len(str(config.get('system_prompt') or ''))}，"
        f"kb={config['kb_ids']}，tools={config['tool_ids']}，"
        f"model={model.name if model else '未配置'}"
    )

    answer, model_note = echo, "离线回显（未调用模型）"
    if model is not None and model.provider != "MOCK":
        from app.services import llm

        try:
            # 草稿测试用于预览提示词效果：直接使用应用自己的 system_prompt，不套用生产侧的事实约束
            result = llm.chat(
                model,
                [
                    {"role": "system", "content": str(config.get("system_prompt") or "你是工业设备售后助手。")},
                    {"role": "user", "content": message},
                ],
                transport=transport,
                timeout=30.0,
            )
            answer = result.content
            model_note = f"真实模型调用（{result.model}，{result.total_tokens} tokens，{result.latency_ms}ms）"
        except llm.LlmError as exc:
            model_note = f"模型调用失败已回退离线回显：{exc.code} {exc.message}"
    return {
        "ok": not problems,
        "problems": problems,
        "answer": answer,
        "model": model.name if model else None,
        "config": config,
        "note": model_note,
    }


def publish(session: Session, app: AIApplication, *, published_by: int | None) -> ApplicationVersion:
    if app.status == "DISABLED":
        raise ApiError(422, "APPLICATION_DISABLED", "已停用应用不可发布")
    problems = validate_for_publish(session, app)
    if problems:
        raise ApiError(422, "PUBLISH_VALIDATION_FAILED", "发布校验失败", {"problems": problems})

    config = normalize_config(app.draft_config)
    next_no = (
        session.execute(
            select(func.max(ApplicationVersion.version_no)).where(
                ApplicationVersion.application_id == app.id
            )
        ).scalar_one()
        or 0
    ) + 1

    # 旧版本标记 SUPERSEDED（内容仍不可变，P1 才支持回滚切换）
    for previous in session.execute(
        select(ApplicationVersion).where(
            ApplicationVersion.application_id == app.id, ApplicationVersion.status == "PUBLISHED"
        )
    ).scalars():
        previous.status = "SUPERSEDED"

    version = ApplicationVersion(
        application_id=app.id,
        version_no=next_no,
        config=config,
        status="PUBLISHED",
        published_by=published_by,
    )
    session.add(version)
    session.flush()

    app.status = "PUBLISHED"
    app.current_version_id = version.id
    session.commit()
    session.refresh(version)
    session.refresh(app)
    return version


def disable(session: Session, app: AIApplication) -> AIApplication:
    app.status = "DISABLED"
    session.commit()
    session.refresh(app)
    return app


def public_view(session: Session, slug: str) -> dict[str, Any]:
    app = session.execute(
        select(AIApplication).where(AIApplication.slug == slug.lower())
    ).scalar_one_or_none()
    if app is None or app.status != "PUBLISHED" or app.current_version_id is None:
        raise ApiError(404, "APPLICATION_NOT_FOUND", "应用不存在或未发布")
    version = session.get(ApplicationVersion, app.current_version_id)
    return {
        "name": app.name,
        "slug": app.slug,
        "description": app.description,
        "version_no": version.version_no if version else None,
        "write_confirmation": bool((version.config if version else {}).get("write_confirmation", True)),
    }
def rollback_to_version(
    session: Session, app: AIApplication, *, version_no: int, actor_id: int | None
) -> ApplicationVersion:
    """P1：切回历史发布快照。快照内容不可变，仅切换 current_version 与草稿。

    权限仍按当前策略校验（调用方负责鉴权），回滚不会放宽任何授权。
    """
    target = session.execute(
        select(ApplicationVersion).where(
            ApplicationVersion.application_id == app.id,
            ApplicationVersion.version_no == version_no,
        )
    ).scalar_one_or_none()
    if target is None:
        raise ApiError(404, "VERSION_NOT_FOUND", "版本不存在")
    if target.status == "PUBLISHED" and app.current_version_id == target.id:
        raise ApiError(409, "VERSION_ALREADY_ACTIVE", "该版本已是当前发布版本")

    for version in session.execute(
        select(ApplicationVersion).where(ApplicationVersion.application_id == app.id)
    ).scalars():
        version.status = "PUBLISHED" if version.id == target.id else "SUPERSEDED"

    app.current_version_id = target.id
    app.status = "PUBLISHED"
    app.draft_config = dict(target.config)
    session.commit()
    session.refresh(target)
    return target


def list_versions(session: Session, app: AIApplication) -> list[ApplicationVersion]:
    return list(
        session.execute(
            select(ApplicationVersion)
            .where(ApplicationVersion.application_id == app.id)
            .order_by(ApplicationVersion.version_no)
        ).scalars()
    )