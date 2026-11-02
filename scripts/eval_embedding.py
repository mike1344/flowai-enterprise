"""CR-006：hash / local(bge) 两套向量的检索对比（离线、可重复）。

用法：
    python scripts/eval_embedding.py                  # 默认对比 hash 与 local
    python scripts/eval_embedding.py --providers hash,local

输出：docs/acceptance/V1.3-Embedding对比-YYYYMMDD.md
"""

import argparse
import io
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "flowai-api"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import build_engine  # noqa: E402
from app.models import (  # noqa: E402
    AIApplication,
    ApplicationKnowledgeBase,
    KnowledgeBase,
    ResourceGrant,
    User,
)
from app.services import auth as auth_service  # noqa: E402
from app.services import kb as kb_service  # noqa: E402
from app.services import rag as rag_service  # noqa: E402

DOCS = {
    "gateway.md": "工业网关 HC200 通信异常处理：先检查网线，再确认电源模块。告警代码 E03 表示链路中断。",
    "power.md": "电源模块 PM100 过热会触发降频保护，需清理散热片并检查风扇。",
    "warranty.md": "HC200 的标准保修期为 24 个月，自安装之日起计算。",
}

# (问题, 期望命中的文档)；期望为 None 表示应当拒答的负例
QUERIES = [
    ("设备联不上网怎么办", "gateway.md"),
    ("告警 E03 是什么问题", "gateway.md"),
    ("链路断了怎么修", "gateway.md"),
    ("网线松了要不要先检查", "gateway.md"),
    ("机器过热会怎样", "power.md"),
    ("PM100 温度太高", "power.md"),
    ("风扇要不要清理", "power.md"),
    ("保修是怎么算的", "warranty.md"),
    ("这台机器还能保修多久", "warranty.md"),
    ("安装后多久过保", "warranty.md"),
    ("今天天气怎么样", None),
    ("给我讲个笑话", None),
    ("帮我写一首诗", None),
    ("公司年会在哪里办", None),
]


def make_settings(db_url: str, provider: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=db_url,
        environment="eval",
        embedding_provider=provider,
        embedding_model="BAAI/bge-small-zh-v1.5" if provider == "local" else "",
    )


def prepare(db_url: str):
    engine = build_engine(db_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(session, username="admin", display_name="管理员", password="Passw0rd!2026")
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
        kb = KnowledgeBase(name="评测知识库")
        session.add(kb)
        session.commit()
        app = AIApplication(
            name="评测应用",
            slug="eval-app",
            status="PUBLISHED",
            draft_config={"model_config_id": 0, "system_prompt": "评测用"},
            created_by=admin.id,
        )
        session.add(app)
        session.commit()
        session.add(ApplicationKnowledgeBase(application_id=app.id, knowledge_base_id=kb.id))
        session.add(
            ResourceGrant(user_id=admin.id, resource_type="KNOWLEDGE_BASE", resource_id=kb.id, permission="READ")
        )
        session.commit()
        ids = {"kb": kb.id, "app": app.id, "user": admin.id}
    engine.dispose()
    return ids


def ingest_all(db_url: str, provider: str, ids: dict, upload_dir: Path) -> None:
    settings = make_settings(db_url, provider)
    engine = build_engine(db_url)
    with Session(engine) as session:
        for name, text in DOCS.items():
            path = upload_dir / name
            path.write_text(text, encoding="utf-8")
            document = kb_service.add_document_metadata(
                session, kb_id=ids["kb"], title=name, filename=name, content_type="text/markdown"
            )
            rag_service.ingest_document(session, document, path, settings=settings)
    engine.dispose()


def run_queries(db_url: str, ids: dict) -> list[dict]:
    engine = build_engine(db_url)
    rows = []
    with Session(engine) as session:
        for query, expected in QUERIES:
            result = rag_service.retrieve(
                session, application_id=ids["app"], user_id=ids["user"], query=query, limit=3
            )
            items = result.get("items") or []
            top = items[0] if items else None
            refused = bool(result.get("refused"))
            hit = refused if expected is None else (bool(top) and top["document_title"] == expected)
            rows.append(
                {
                    "query": query,
                    "expected": expected,
                    "refused": refused,
                    "top": top["document_title"] if top else None,
                    "score": top["score"] if top else None,
                    "hit": hit,
                }
            )
    engine.dispose()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default="hash,local")
    parser.add_argument("--out-dir", default=str(ROOT / "docs" / "acceptance"))
    args = parser.parse_args()
    providers = [item.strip() for item in args.providers.split(",") if item.strip()]

    workdir = Path(tempfile.mkdtemp(prefix="emb-eval-"))
    results: dict[str, list[dict]] = {}
    for provider in providers:
        db_url = f"sqlite:///{workdir / (provider + '.db')}"
        ids = prepare(db_url)
        ingest_all(db_url, provider, ids, workdir)
        results[provider] = run_queries(db_url, ids)
        hits = sum(1 for row in results[provider] if row["hit"])
        print(f"{provider}: hit={hits}/{len(QUERIES)}")

    lines = [
        f"# V1.3 Embedding 对比（hash vs local bge）— {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "- 语料：3 篇设备文档（网关/电源/保修）；问题为**语义改写**，尽量不与原文用词重合。",
        "- 判定：top1 命中期望文档记为 hit；`拒答` 表示相似度低于阈值被拒。",
        "",
        "| 提供者 | 命中 | 拒答 |",
        "|---|---|---|",
    ]
    for provider, rows in results.items():
        hits = sum(1 for row in rows if row["hit"])
        refused = sum(1 for row in rows if row["refused"])
        lines.append(f"| {provider} | {hits}/{len(QUERIES)} | {refused} |")

    for provider, rows in results.items():
        lines += ["", f"## {provider}", "", "| 问题 | 期望 | top1 | 分数 | 命中 |", "|---|---|---|---|---|"]
        for row in rows:
            lines.append(
                f"| {row['query']} | {row['expected']} | {row['top'] or '—'} | "
                f"{row['score'] if row['score'] is not None else '—'} | {'✅' if row['hit'] else '❌'} |"
            )

    report = Path(args.out_dir) / f"V1.3-Embedding对比-{datetime.now():%Y%m%d}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("report:", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())