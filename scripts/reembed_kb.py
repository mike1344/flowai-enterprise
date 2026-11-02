"""CR-006：按当前 Embedding 提供者重建知识库向量（切换 provider 后必须执行）。

用法（容器内，仓库挂在 /repo）：
    docker compose run --rm -v F:/Y1:/repo -w /repo \
        -e FLOWAI_EMBEDDING_PROVIDER=local flowai-api python scripts/reembed_kb.py --all

说明：
- 旧索引保留为 DEPRECATED，可随时用 `POST /knowledge-bases/{id}/indexes/{index_id}/activate` 切回；
- 只改 `document_chunk.embedding` 与 `index_version`，不动文档内容与权限；
- 失败时索引标记 FAILED，旧的 active 索引不受影响。
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "services" / "flowai-api"
sys.path.insert(0, str(SERVICE_ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import build_engine  # noqa: E402
from app.models import Document, DocumentChunk, IndexVersion, KnowledgeBase  # noqa: E402
from app.services import embeddings  # noqa: E402

BATCH = 32


def reembed_kb(session: Session, kb_id: int, settings, dry_run: bool = False) -> dict:
    kb = session.get(KnowledgeBase, kb_id)
    if kb is None:
        return {"kb_id": kb_id, "error": "NOT_FOUND"}

    rows = session.execute(
        select(DocumentChunk.id, DocumentChunk.content)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.knowledge_base_id == kb_id, Document.deleted_at.is_(None))
    ).all()
    provider = embeddings.provider(settings)
    if dry_run:
        return {
            "kb_id": kb_id,
            "kb": kb.name,
            "chunks": len(rows),
            "provider": provider,
            "model": embeddings.model_name(settings),
            "dim": embeddings.dimension(settings),
            "dry_run": True,
        }

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
        embedding_provider=provider,
        embedding_model=embeddings.model_name(settings),
        embedding_dim=embeddings.dimension(settings),
    )
    session.add(version)
    session.flush()

    try:
        for start in range(0, len(rows), BATCH):
            batch = rows[start : start + BATCH]
            vectors = embeddings.embed_many([row.content for row in batch], settings)
            for row, vector in zip(batch, vectors):
                chunk = session.get(DocumentChunk, row.id)
                chunk.embedding = json.dumps([round(value, 6) for value in vector])
            session.flush()

        version.status = "READY"
        version.chunk_count = len(rows)
        for previous in session.execute(
            select(IndexVersion).where(
                IndexVersion.knowledge_base_id == kb_id, IndexVersion.is_active.is_(True)
            )
        ).scalars():
            previous.is_active = False
            previous.status = "DEPRECATED"
        version.is_active = True
        session.commit()
        return {
            "kb_id": kb_id,
            "kb": kb.name,
            "chunks": len(rows),
            "version_no": next_no,
            "provider": provider,
            "model": embeddings.model_name(settings),
            "dim": embeddings.dimension(settings),
        }
    except Exception as exc:  # noqa: BLE001 - 失败必须可见，旧索引保持可用
        session.rollback()
        failed = session.get(IndexVersion, version.id)
        if failed is not None:
            failed.status = "FAILED"
            failed.is_active = False
        session.commit()
        return {"kb_id": kb_id, "kb": kb.name, "error": str(exc)[:300]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-id", type=int, action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        print("缺少 FLOWAI_DATABASE_URL")
        return 2

    engine = build_engine(settings.database_url)
    results = []
    with Session(engine) as session:
        kb_ids = args.kb_id
        if args.all or not kb_ids:
            kb_ids = list(session.execute(select(KnowledgeBase.id)).scalars())
        for kb_id in kb_ids:
            results.append(reembed_kb(session, kb_id, settings, dry_run=args.dry_run))
    engine.dispose()

    for item in results:
        print(json.dumps(item, ensure_ascii=False))
    failed = [item for item in results if item.get("error")]
    print(f"SUMMARY total={len(results)} failed={len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())