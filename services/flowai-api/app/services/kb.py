"""知识库服务：共享绑定、检索权限过滤、朴素检索（M03-01）。"""

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import (
    AIApplication,
    ApplicationKnowledgeBase,
    Document,
    DocumentChunk,
    KnowledgeBase,
    ResourceGrant,
)


def create_kb(session: Session, *, name: str, description: str | None, created_by: int | None) -> KnowledgeBase:
    existing = session.execute(
        select(KnowledgeBase).where(KnowledgeBase.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise ApiError(409, "KB_NAME_TAKEN", "知识库名称已存在")
    kb = KnowledgeBase(name=name, description=description, status="ACTIVE", created_by=created_by)
    session.add(kb)
    session.commit()
    session.refresh(kb)
    return kb


def get_kb(session: Session, kb_id: int) -> KnowledgeBase:
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise ApiError(404, "KB_NOT_FOUND", "知识库不存在")
    return kb


def bind_application(session: Session, application_id: int, kb_id: int) -> ApplicationKnowledgeBase:
    app = session.get(AIApplication, application_id)
    if app is None:
        raise ApiError(404, "APPLICATION_NOT_FOUND", "应用不存在")
    get_kb(session, kb_id)
    existing = session.execute(
        select(ApplicationKnowledgeBase).where(
            ApplicationKnowledgeBase.application_id == application_id,
            ApplicationKnowledgeBase.knowledge_base_id == kb_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    link = ApplicationKnowledgeBase(application_id=application_id, knowledge_base_id=kb_id)
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def unbind_application(session: Session, application_id: int, kb_id: int) -> bool:
    link = session.execute(
        select(ApplicationKnowledgeBase).where(
            ApplicationKnowledgeBase.application_id == application_id,
            ApplicationKnowledgeBase.knowledge_base_id == kb_id,
        )
    ).scalar_one_or_none()
    if link is None:
        return False
    session.delete(link)
    session.commit()
    return True


def bound_kb_ids(session: Session, application_id: int) -> list[int]:
    rows = session.execute(
        select(ApplicationKnowledgeBase.knowledge_base_id).where(
            ApplicationKnowledgeBase.application_id == application_id
        )
    ).scalars()
    return sorted(rows.all())


def user_kb_scope(session: Session, user_id: int) -> set[int]:
    """用户被授权的知识库集合（ResourceGrant READ/USE/MANAGE 均视为可读）。"""
    rows = session.execute(
        select(ResourceGrant.resource_id).where(
            ResourceGrant.user_id == user_id,
            ResourceGrant.resource_type == "KNOWLEDGE_BASE",
            ResourceGrant.permission.in_(("READ", "USE", "MANAGE")),
        )
    ).scalars()
    return set(rows.all())


def add_document_metadata(
    session: Session,
    *,
    kb_id: int,
    title: str,
    filename: str = "",
    content_type: str = "text/plain",
    size_bytes: int = 0,
) -> Document:
    get_kb(session, kb_id)
    document = Document(
        knowledge_base_id=kb_id,
        title=title,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        status="PENDING",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def list_documents(session: Session, kb_id: int) -> list[Document]:
    return (
        session.execute(
            select(Document)
            .where(Document.knowledge_base_id == kb_id, Document.deleted_at.is_(None))
            .order_by(Document.id)
        )
        .scalars()
        .all()
    )


def naive_search(
    session: Session,
    *,
    application_id: int,
    user_id: int,
    query: str,
    limit: int = 5,
) -> dict[str, Any]:
    """M03-01 的朴素检索：验证权限链路（向量检索在 M03-03 替换）。"""
    allowed_kbs = user_kb_scope(session, user_id)
    app_kbs = set(bound_kb_ids(session, application_id))
    effective = sorted(allowed_kbs & app_kbs)

    if not app_kbs:
        return {"items": [], "effective_kb_ids": [], "reason": "APP_HAS_NO_KB"}
    if not effective:
        return {
            "items": [],
            "effective_kb_ids": [],
            "reason": "NO_RESOURCE_GRANT",
            "app_kb_ids": sorted(app_kbs),
        }

    pattern = f"%{query.strip()}%"
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id.in_(effective),
            Document.deleted_at.is_(None),
            Document.status == "READY",
            or_(DocumentChunk.content.ilike(pattern), Document.title.ilike(pattern)),
        )
        .order_by(DocumentChunk.id)
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    items = [
        {
            "document_id": document.id,
            "document_title": document.title,
            "kb_id": document.knowledge_base_id,
            "chunk_id": chunk.id,
            "page_label": chunk.page_label,
            "section": chunk.section,
            "snippet": chunk.content[:200],
        }
        for chunk, document in rows
    ]
    return {"items": items, "effective_kb_ids": effective}


def kb_stats(session: Session, kb_id: int) -> dict[str, int]:
    documents = session.execute(
        select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb_id)
    ).scalar_one()
    ready = session.execute(
        select(func.count())
        .select_from(Document)
        .where(Document.knowledge_base_id == kb_id, Document.status == "READY")
    ).scalar_one()
    chunks = session.execute(
        select(func.count())
        .select_from(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.knowledge_base_id == kb_id)
    ).scalar_one()
    return {"documents": documents, "ready_documents": ready, "chunks": chunks}