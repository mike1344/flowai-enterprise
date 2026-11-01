"""文档上传、重处理与状态（M03-02）。"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_permission, verify_csrf
from app.core.errors import ApiError, ok
from app.models import Document, DocumentChunk
from app.services import kb as kb_service
from app.services import rag as rag_service

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("/knowledge-bases/{kb_id}/documents/upload", status_code=202)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    current: CurrentUser = Depends(require_permission("kb:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    """上传即同步摄取（P0 单机）；状态 PENDING→PROCESSING→READY/FAILED 全部落库可查。"""
    kb_service.get_kb(session, kb_id)
    payload = await file.read()
    if not payload:
        raise ApiError(400, "INVALID_REQUEST", "文件为空")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ApiError(400, "FILE_TOO_LARGE", "文件超过 20MB 限制")

    kind = rag_service.detect_kind(file.content_type or "", file.filename or "")
    path = rag_service.save_upload(kb_id, file.filename or "upload", payload)
    document = kb_service.add_document_metadata(
        session,
        kb_id=kb_id,
        title=file.filename or "未命名文档",
        filename=file.filename or "",
        content_type=file.content_type or "text/plain",
        size_bytes=len(payload),
    )
    result = rag_service.ingest_document(session, document, path)
    return ok(
        {
            "id": result.id,
            "kind": kind,
            "status": result.status,
            "error_message": result.error_message,
        },
        "文档摄取完成" if result.status == "READY" else "文档摄取失败",
    )


@router.post("/documents/{document_id}/reprocess")
async def reprocess_document(
    document_id: int,
    current: CurrentUser = Depends(require_permission("kb:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    document = session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在")

    candidates = sorted(rag_service.UPLOAD_ROOT.glob(f"kb{document.knowledge_base_id}_*"))
    match = [path for path in candidates if document.filename and document.filename in path.name]
    if not match:
        raise ApiError(422, "SOURCE_FILE_MISSING", "原始文件缺失，无法重处理")

    result = rag_service.ingest_document(session, document, Path(match[-1]))
    return ok(
        {"id": result.id, "status": result.status, "error_message": result.error_message},
        "重处理完成" if result.status == "READY" else "重处理失败",
    )


@router.get("/documents/{document_id}")
async def document_status(
    document_id: int,
    current: CurrentUser = Depends(require_permission("kb:manage")),
    session: Session = Depends(get_db),
) -> dict:
    document = session.get(Document, document_id)
    if document is None:
        raise ApiError(404, "DOCUMENT_NOT_FOUND", "文档不存在")
    chunk_count = session.execute(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
    ).scalar_one()
    return ok(
        {
            "id": document.id,
            "title": document.title,
            "status": document.status,
            "error_message": document.error_message,
            "chunk_count": chunk_count,
        },
        "文档状态",
    )