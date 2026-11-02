"""AI 应用管理接口与公开入口（M02-03）。"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_permission, verify_csrf
from app.core.errors import ApiError, ok
from app.models import AIApplication, ApplicationVersion
from app.services import applications as app_service

router = APIRouter()


class _Strict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class AppCreate(_Strict):
    name: str = Field(min_length=1, max_length=80)
    slug: str = Field(min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    config: dict[str, Any] | None = None


class AppUpdate(_Strict):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    slug: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    config: dict[str, Any] | None = None


class DraftTestRequest(_Strict):
    message: str = Field(min_length=1, max_length=2000)


def serialize(app: AIApplication) -> dict[str, Any]:
    return {
        "id": app.id,
        "name": app.name,
        "slug": app.slug,
        "description": app.description,
        "status": app.status,
        "draft_config": app.draft_config,
        "current_version_id": app.current_version_id,
        "public_path": f"/apps/{app.slug}",
    }


def _get(session: Session, app_id: int) -> AIApplication:
    app = session.get(AIApplication, app_id)
    if app is None:
        raise ApiError(404, "APPLICATION_NOT_FOUND", "应用不存在")
    return app


@router.post("/applications", status_code=201)
async def create_application(
    payload: AppCreate,
    current: CurrentUser = Depends(require_permission("app:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    app = app_service.create_application(
        session,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        config=payload.config,
        created_by=current.user.id,
    )
    return ok(serialize(app), "应用创建成功")


@router.get("/applications")
async def list_applications(
    current: CurrentUser = Depends(require_permission("app:manage")),
    session: Session = Depends(get_db),
) -> dict:
    rows = session.execute(select(AIApplication).order_by(AIApplication.id)).scalars().all()
    return ok({"items": [serialize(row) for row in rows], "total": len(rows)}, "应用列表")


@router.get("/applications/{app_id}")
async def get_application(
    app_id: int,
    current: CurrentUser = Depends(require_permission("app:manage")),
    session: Session = Depends(get_db),
) -> dict:
    return ok(serialize(_get(session, app_id)), "应用详情")


@router.patch("/applications/{app_id}")
async def update_application(
    app_id: int,
    payload: AppUpdate,
    current: CurrentUser = Depends(require_permission("app:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    app = _get(session, app_id)
    updated = app_service.update_draft(session, app, **payload.model_dump(exclude_none=True))
    return ok(serialize(updated), "草稿已更新")


@router.post("/applications/{app_id}/test")
def test_application(
    app_id: int,
    payload: DraftTestRequest,
    request: Request,
    current: CurrentUser = Depends(require_permission("app:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    app = _get(session, app_id)
    result = app_service.run_draft_test(
        session, app, payload.message, transport=getattr(request.app.state, "llm_transport", None)
    )
    if app.status in {"DRAFT", "TESTING"}:
        app.status = "TESTING"
        session.commit()
    return ok(result, "草稿测试完成" if result["ok"] else "草稿测试存在问题")


@router.post("/applications/{app_id}/publish")
async def publish_application(
    app_id: int,
    request: Request,
    current: CurrentUser = Depends(require_permission("app:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    app = _get(session, app_id)
    version = app_service.publish(session, app, published_by=current.user.id)
    from app.services import audit as audit_service

    audit_service.record(
        session,
        action="application.publish",
        actor_ref=current.user.username,
        trace_id=getattr(request.state, "trace_id", None),
        resource_type="APPLICATION",
        resource_id=app.id,
        detail={"version_no": version.version_no},
    )
    session.commit()
    return ok(
        {
            "application_id": app.id,
            "version_id": version.id,
            "version_no": version.version_no,
            "status": app.status,
            "public_path": f"/apps/{app.slug}",
        },
        "应用已发布",
    )


@router.post("/applications/{app_id}/disable")
async def disable_application(
    app_id: int,
    current: CurrentUser = Depends(require_permission("app:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    app = app_service.disable(session, _get(session, app_id))
    return ok(serialize(app), "应用已停用")


@router.get("/applications/{app_id}/versions")
async def list_versions(
    app_id: int,
    current: CurrentUser = Depends(require_permission("app:manage")),
    session: Session = Depends(get_db),
) -> dict:
    app = _get(session, app_id)
    rows = session.execute(
        select(ApplicationVersion)
        .where(ApplicationVersion.application_id == app.id)
        .order_by(ApplicationVersion.version_no)
    ).scalars()
    return ok(
        {
            "items": [
                {
                    "version_id": row.id,
                    "version_no": row.version_no,
                    "status": row.status,
                    "published_at": row.published_at.isoformat(),
                    "config": row.config,
                }
                for row in rows
            ]
        },
        "版本历史",
    )


@router.get("/apps/{slug}")
async def public_application(
    slug: str,
    session: Session = Depends(get_db),
) -> dict:
    """已发布应用的公开入口信息；未发布/停用一律 404（不泄露存在性）。"""
    return ok(app_service.public_view(session, slug), "应用公开信息")
@router.post("/applications/{app_id}/versions/{version_no}/rollback")
async def rollback_application(
    app_id: int,
    version_no: int,
    request: Request,
    current: CurrentUser = Depends(require_permission("app:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    app = _get(session, app_id)
    version = app_service.rollback_to_version(
        session, app, version_no=version_no, actor_id=current.user.id
    )
    from app.services import audit as audit_service

    audit_service.record(
        session,
        action="application.rollback",
        actor_ref=current.user.username,
        trace_id=getattr(request.state, "trace_id", None),
        resource_type="APPLICATION",
        resource_id=app.id,
        detail={"version_no": version.version_no},
    )
    session.commit()
    return ok(
        {
            "application_id": app.id,
            "version_id": version.id,
            "version_no": version.version_no,
            "status": app.status,
            "public_path": f"/apps/{app.slug}",
        },
        "已切换到历史版本",
    )