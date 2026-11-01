"""知识库接口（M03-01）：共享绑定、文档元数据、权限过滤检索。"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db, require_permission, verify_csrf
from app.core.errors import ApiError, ok
from app.models import KnowledgeBase
from app.services import kb as kb_service
from app.services import rag as rag_service

router = APIRouter()


class _Strict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class KBCreate(_Strict):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)


class DocumentCreate(_Strict):
    title: str = Field(min_length=1, max_length=200)
    filename: str = Field(default="", max_length=255)
    content_type: str = Field(default="text/plain", max_length=80)
    size_bytes: int = Field(default=0, ge=0)


class SearchRequest(_Strict):
    application_id: int = Field(gt=0)
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


def serialize_kb(kb: KnowledgeBase, stats: dict[str, int]) -> dict[str, Any]:
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "status": kb.status,
        "stats": stats,
    }


@router.post("/knowledge-bases", status_code=201)
async def create_kb(
    payload: KBCreate,
    current: CurrentUser = Depends(require_permission("kb:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    kb = kb_service.create_kb(
        session, name=payload.name, description=payload.description, created_by=current.user.id
    )
    return ok(serialize_kb(kb, kb_service.kb_stats(session, kb.id)), "知识库创建成功")


@router.get("/knowledge-bases")
async def list_kbs(
    current: CurrentUser = Depends(require_permission("kb:manage")),
    session: Session = Depends(get_db),
) -> dict:
    rows = session.execute(select(KnowledgeBase).order_by(KnowledgeBase.id)).scalars().all()
    return ok(
        {
            "items": [serialize_kb(row, kb_service.kb_stats(session, row.id)) for row in rows],
            "total": len(rows),
        },
        "知识库列表",
    )


@router.get("/knowledge-bases/{kb_id}")
async def get_kb(
    kb_id: int,
    current: CurrentUser = Depends(require_permission("kb:manage")),
    session: Session = Depends(get_db),
) -> dict:
    kb = kb_service.get_kb(session, kb_id)
    return ok(serialize_kb(kb, kb_service.kb_stats(session, kb.id)), "知识库详情")


@router.post("/knowledge-bases/{kb_id}/documents", status_code=201)
async def add_document(
    kb_id: int,
    payload: DocumentCreate,
    current: CurrentUser = Depends(require_permission("kb:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    document = kb_service.add_document_metadata(
        session,
        kb_id=kb_id,
        title=payload.title,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
    )
    return ok(
        {
            "id": document.id,
            "knowledge_base_id": document.knowledge_base_id,
            "title": document.title,
            "status": document.status,
        },
        "文档已登记（解析任务在 M03-02 接入）",
    )


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_documents(
    kb_id: int,
    current: CurrentUser = Depends(require_permission("kb:manage")),
    session: Session = Depends(get_db),
) -> dict:
    kb_service.get_kb(session, kb_id)
    rows = kb_service.list_documents(session, kb_id)
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "title": row.title,
                    "status": row.status,
                    "content_type": row.content_type,
                    "size_bytes": row.size_bytes,
                    "error_message": row.error_message,
                }
                for row in rows
            ],
            "total": len(rows),
        },
        "文档列表",
    )


@router.post("/applications/{application_id}/knowledge-bases/{kb_id}")
async def bind_kb(
    application_id: int,
    kb_id: int,
    current: CurrentUser = Depends(require_permission("app:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    link = kb_service.bind_application(session, application_id, kb_id)
    return ok(
        {"application_id": link.application_id, "knowledge_base_id": link.knowledge_base_id},
        "知识库已绑定应用",
    )


@router.delete("/applications/{application_id}/knowledge-bases/{kb_id}")
async def unbind_kb(
    application_id: int,
    kb_id: int,
    current: CurrentUser = Depends(require_permission("app:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    removed = kb_service.unbind_application(session, application_id, kb_id)
    if not removed:
        raise ApiError(404, "BINDING_NOT_FOUND", "绑定不存在")
    return ok({"removed": True}, "绑定已解除")


@router.post("/knowledge-bases/search-test")
async def search_test(
    payload: SearchRequest,
    current: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """检索测试：权限 = 用户资源授权 ∩ 应用绑定 ∩ 文档可见。"""
    result = rag_service.answer_with_evidence(
        session,
        application_id=payload.application_id,
        user_id=current.user.id,
        query=payload.query,
        limit=payload.limit,
    )
    return ok(result, "检索测试完成")