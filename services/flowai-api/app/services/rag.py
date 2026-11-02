"""RAG 摄取与检索（M03-02/M03-03）：解析、分块、离线向量、引用与拒答。"""

import hashlib
import io
import json
import math
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.models import (
    ApplicationKnowledgeBase,
    Document,
    DocumentChunk,
    DocumentVersion,
    IndexVersion,
    KnowledgeBase,
    ResourceGrant,
)
from app.services import embeddings

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
EMBED_DIM = 256
REFUSAL_THRESHOLD = 0.18  # hash 提供者的默认阈值（CR-006 起按提供者区分）
PROVIDER_THRESHOLDS = {"hash": 0.18, "local": 0.45, "openai": 0.35}
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "data" / "uploads"

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
}


# ------------------------------------------------------------------ 解析
def detect_kind(content_type: str, filename: str) -> str:
    kind = ALLOWED_TYPES.get(content_type)
    if kind:
        return kind
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in {"pdf", "docx", "txt", "md"}:
        return suffix
    raise ApiError(400, "UNSUPPORTED_FILE_TYPE", "仅支持 PDF / DOCX / TXT / Markdown")


def extract_text(path: Path, kind: str) -> str:
    if kind == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if kind == "docx":
        import docx

        document = docx.Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
    return path.read_text(encoding="utf-8", errors="replace").strip()


# ------------------------------------------------------------------ 分块与向量
def split_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    cleaned = re.sub(r"\r\n?", "\n", text).strip()
    if not cleaned:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 1 <= size:
            buffer = f"{buffer}\n{paragraph}".strip()
            continue
        if buffer:
            chunks.append(buffer)
            tail = buffer[-overlap:] if overlap else ""
            buffer = f"{tail}\n{paragraph}".strip()
        else:
            for start in range(0, len(paragraph), size - overlap):
                chunks.append(paragraph[start : start + size])
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return [chunk for chunk in chunks if chunk.strip()]


def tokenize(text: str) -> list[str]:
    """兼容入口：hash 提供者的分词实现（CR-006 起统一在 embeddings 模块）。"""
    return embeddings.tokenize(text)


def embed(text: str, settings: Settings | None = None) -> list[float]:
    """兼容入口：按配置的提供者生成向量（默认 hash，保持离线可跑）。"""
    return embeddings.embed(text, settings)


def refusal_threshold(settings: Settings | None = None) -> float:
    """阈值随向量空间变化：bge 的无关问题相似度约 0.28～0.30，hash 只有 0.1 左右。"""
    settings = settings or get_settings()
    if settings.rag_refusal_threshold and settings.rag_refusal_threshold > 0:
        return float(settings.rag_refusal_threshold)
    return PROVIDER_THRESHOLDS.get(embeddings.provider(settings), REFUSAL_THRESHOLD)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ------------------------------------------------------------------ 索引
def current_active_index(session: Session, kb_id: int) -> IndexVersion | None:
    return session.execute(
        select(IndexVersion).where(
            IndexVersion.knowledge_base_id == kb_id, IndexVersion.is_active.is_(True)
        )
    ).scalar_one_or_none()


def _new_index_version(
    session: Session, kb_id: int, settings: Settings | None = None
) -> IndexVersion:
    settings = settings or get_settings()
    next_no = (
        session.execute(
            select(func.max(IndexVersion.version_no)).where(IndexVersion.knowledge_base_id == kb_id)
        ).scalar_one()
        or 0
    ) + 1
    version = IndexVersion(
        knowledge_base_id=kb_id,
        version_no=next_no,
        status="BUILDING",
        is_active=False,
        embedding_provider=embeddings.provider(settings),
        embedding_model=embeddings.model_name(settings),
        embedding_dim=embeddings.dimension(settings),
    )
    session.add(version)
    session.flush()
    return version


def ingest_document(
    session: Session,
    document: Document,
    raw_path: Path,
    settings: Settings | None = None,
) -> Document:
    """解析 → 分块 → 向量 → 文档 READY → 索引就绪切换。失败写入 FAILED 且不动旧索引。"""
    settings = settings or get_settings()
    kind = detect_kind(document.content_type, document.filename or document.title)
    index_version = _new_index_version(session, document.knowledge_base_id, settings)
    index_version_id = index_version.id
    try:
        document.status = "PROCESSING"
        session.commit()

        text = extract_text(raw_path, kind)
        if not text:
            raise ValueError("文档无可解析文本")
        chunks = split_chunks(text)
        if not chunks:
            raise ValueError("文档分块为空")

        session.execute(
            DocumentChunk.__table__.delete().where(DocumentChunk.document_id == document.id)
        )
        vectors = embeddings.embed_many(chunks, settings)
        for index, content in enumerate(chunks):
            vector = vectors[index]
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    token_estimate=max(1, len(content) // 4),
                    embedding=json.dumps(vector),
                )
            )

        next_no = (
            session.execute(
                select(func.max(DocumentVersion.version_no)).where(
                    DocumentVersion.document_id == document.id
                )
            ).scalar_one()
            or 0
        ) + 1
        session.add(
            DocumentVersion(document_id=document.id, version_no=next_no, chunk_count=len(chunks))
        )

        document.status = "READY"
        document.error_message = None
        index_version.status = "READY"
        # 会话是 autoflush=False：统计前必须显式 flush，否则首次摄取会把 chunk_count 记成 0
        session.flush()
        index_version.chunk_count = session.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.knowledge_base_id == document.knowledge_base_id)
        ).scalar_one()
        for previous in session.execute(
            select(IndexVersion).where(
                IndexVersion.knowledge_base_id == document.knowledge_base_id,
                IndexVersion.is_active.is_(True),
            )
        ).scalars():
            previous.is_active = False
            previous.status = "DEPRECATED"
        index_version.is_active = True
        session.commit()
        session.refresh(document)
        return document
    except Exception as exc:  # noqa: BLE001 - 失败必须可见且不影响旧索引
        session.rollback()
        failed_version = session.get(IndexVersion, index_version_id)
        if failed_version is not None:
            failed_version.status = "FAILED"
            failed_version.is_active = False
        current = session.get(Document, document.id)
        if current is not None:
            current.status = "FAILED"
            current.error_message = str(exc)[:500]
        session.commit()
        if current is not None:
            session.refresh(current)
            return current
        return document


def save_upload(kb_id: int, filename: str, payload: bytes) -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", filename or "upload.bin")
    target = UPLOAD_ROOT / f"kb{kb_id}_{hashlib.sha256(payload).hexdigest()[:12]}_{safe_name}"
    target.write_bytes(payload)
    return target


# ------------------------------------------------------------------ 检索
def user_kb_scope(session: Session, user_id: int) -> set[int]:
    rows = session.execute(
        select(ResourceGrant.resource_id).where(
            ResourceGrant.user_id == user_id,
            ResourceGrant.resource_type == "KNOWLEDGE_BASE",
            ResourceGrant.permission.in_(("READ", "USE", "MANAGE")),
        )
    ).scalars()
    return set(rows.all())


def app_kb_scope(session: Session, application_id: int) -> set[int]:
    rows = session.execute(
        select(ApplicationKnowledgeBase.knowledge_base_id).where(
            ApplicationKnowledgeBase.application_id == application_id
        )
    ).scalars()
    return set(rows.all())


def retrieve(
    session: Session,
    *,
    application_id: int,
    user_id: int,
    query: str,
    limit: int = 5,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    app_kbs = app_kb_scope(session, application_id)
    grants = user_kb_scope(session, user_id)
    effective = sorted(app_kbs & grants)

    if not app_kbs:
        return {"items": [], "citations": [], "refused": True, "reason": "APP_HAS_NO_KB"}
    if not effective:
        return {"items": [], "citations": [], "refused": True, "reason": "NO_RESOURCE_GRANT"}

    index = current_active_index(session, effective[0]) if len(effective) == 1 else None
    if index is not None and index.status != "READY":
        return {"items": [], "citations": [], "refused": True, "reason": "INDEX_NOT_READY"}

    # 查询向量必须与索引同源：换过 provider 的旧索引不能拿新维度的向量去比
    embed_settings = settings
    if index is not None and index.embedding_provider:
        embed_settings = settings.model_copy(
            update={
                "embedding_provider": index.embedding_provider,
                "embedding_model": index.embedding_model or settings.embedding_model,
                "embedding_dim": index.embedding_dim or settings.embedding_dim,
            }
        )
    query_vector = embeddings.embed(query, embed_settings)

    candidates = session.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id.in_(effective),
            Document.deleted_at.is_(None),
            Document.status == "READY",
        )
    ).all()

    scored: list[tuple[float, DocumentChunk, Document]] = []
    for chunk, document in candidates:
        vector = json.loads(chunk.embedding) if chunk.embedding else embeddings.embed(chunk.content, embed_settings)
        if len(vector) != len(query_vector):  # 维度不一致=旧索引残留，跳过而不是算出错误分数
            continue
        scored.append((cosine(query_vector, vector), chunk, document))
    scored.sort(key=lambda item: item[0], reverse=True)
    top = [item for item in scored[:limit] if item[0] >= refusal_threshold(embed_settings)]

    if not top:
        return {"items": [], "citations": [], "refused": True, "reason": "NO_EVIDENCE"}

    items = []
    citations = []
    for score, chunk, document in top:
        items.append(
            {
                "document_id": document.id,
                "document_title": document.title,
                "kb_id": document.knowledge_base_id,
                "chunk_id": chunk.id,
                "page_label": chunk.page_label or "页码不可用",
                "section": chunk.section,
                "snippet": chunk.content[:240],
                "score": round(score, 4),
            }
        )
        citations.append(
            {
                "document_id": document.id,
                "document_title": document.title,
                "page_label": chunk.page_label or "页码不可用",
                "chunk_id": chunk.id,
            }
        )
    return {
        "items": items,
        "citations": citations,
        "refused": False,
        "effective_kb_ids": effective,
        "evidence_count": len(items),
    }


def answer_with_evidence(session: Session, settings: Settings | None = None, **kwargs) -> dict[str, Any]:
    """无证据必须拒答；有证据返回带引用的答案（P0 抽取式）。"""
    result = retrieve(session, settings=settings, **kwargs)
    if result["refused"]:
        reasons = {
            "APP_HAS_NO_KB": "该应用尚未绑定知识库。",
            "NO_RESOURCE_GRANT": "你没有该知识库的访问授权。",
            "NO_EVIDENCE": "知识库中没有找到可靠依据，无法回答。",
            "INDEX_NOT_READY": "索引尚未就绪，请稍后再试。",
        }
        result["answer"] = reasons.get(result["reason"], "无法回答。")
        return result
    top = result["items"][0]
    result["answer"] = f"依据《{top['document_title']}》：{top['snippet']}"
    return result
def list_index_versions(session: Session, kb_id: int) -> list[IndexVersion]:
    return list(
        session.execute(
            select(IndexVersion)
            .where(IndexVersion.knowledge_base_id == kb_id)
            .order_by(IndexVersion.version_no)
        ).scalars()
    )


def activate_index_version(session: Session, kb_id: int, index_id: int) -> IndexVersion:
    """P1：切回历史 READY 索引；只有 READY 可被激活，失败/构建中不可切换。"""
    target = session.get(IndexVersion, index_id)
    if target is None or target.knowledge_base_id != kb_id:
        raise ApiError(404, "INDEX_NOT_FOUND", "索引版本不存在")
    if target.status not in {"READY", "DEPRECATED"}:
        raise ApiError(422, "INDEX_NOT_READY", "只有 READY 索引可被切换")
    if target.is_active:
        raise ApiError(409, "INDEX_ALREADY_ACTIVE", "该索引已是当前版本")

    for version in session.execute(
        select(IndexVersion).where(IndexVersion.knowledge_base_id == kb_id)
    ).scalars():
        if version.id == target.id:
            version.is_active = True
            version.status = "READY"
        elif version.is_active:
            version.is_active = False
            if version.status == "READY":
                version.status = "DEPRECATED"
    session.commit()
    session.refresh(target)
    return target