"""FlowAI 合成种子：平台账号、角色、模型、应用、知识库与授权（幂等）。

用法（在 services/flowai-api 下，需已配置 FLOWAI_DATABASE_URL）：
    .venv/Scripts/python.exe ../../seed/flowai_seed.py
"""

import io
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1] / "services" / "flowai-api"
sys.path.insert(0, str(SERVICE_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import build_engine  # noqa: E402
from app.models import AIApplication, KnowledgeBase, ModelConfig, ResourceGrant, User  # noqa: E402
from app.services import applications as app_service  # noqa: E402
from app.services import auth as auth_service  # noqa: E402
from app.services import kb as kb_service  # noqa: E402
from app.services import rag as rag_service  # noqa: E402
from app.services import tools as tool_service  # noqa: E402

PASSWORD = "Passw0rd!2026"

KB_DOCS = {
    "gateway.md": (
        "工业网关 HC200 通信异常处理：先检查网线连接，再确认电源模块指示灯。"
        "告警代码 E03 表示链路中断，需检查交换机端口。"
    ),
    "warranty.md": "HC200 标准保修期为 24 个月，自安装之日起计算；延保需另行签署服务合同。",
    "power.md": "电源模块 PM100 过热会触发降频保护，需清理散热片并检查机柜通风。",
}


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("FLOWAI_DATABASE_URL 未配置", file=sys.stderr)
        return 2

    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    created = {}

    with Session(engine) as session:
        auth_service.seed_rbac(session)
        tool_service.seed_tools(session)

        admin = session.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
        if admin is None:
            admin = auth_service.create_user(
                session, username="admin", display_name="平台管理员", password=PASSWORD
            )
            auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
            created["admin"] = 1

        model = session.execute(
            select(ModelConfig).where(ModelConfig.name == "mock-llm")
        ).scalar_one_or_none()
        if model is None:
            model = ModelConfig(
                name="mock-llm",
                provider="MOCK",
                model_name="mock-1",
                base_url="",
                api_key_ref="",
                temperature=0.2,
                max_tokens=1024,
                status="ACTIVE",
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            created["model"] = 1

        app = session.execute(
            select(AIApplication).where(AIApplication.slug == "service-agent")
        ).scalar_one_or_none()
        if app is None:
            app = app_service.create_application(
                session,
                name="售后助手",
                slug="service-agent",
                description="设备故障咨询 → 维修工单闭环",
                config={
                    "model_config_id": model.id,
                    "system_prompt": "你是售后助手，回答必须基于证据，创建工单前必须让用户确认。",
                },
                created_by=admin.id,
            )
            created["application"] = 1
        for code in (
            "get_device_info",
            "get_device_faults",
            "get_device_tickets",
            "get_ticket_status",
            "search_technical_docs",
            "create_repair_ticket",
        ):
            tool_service.bind_tool(session, app.id, code)

        kb = session.execute(
            select(KnowledgeBase).where(KnowledgeBase.name == "设备知识库")
        ).scalar_one_or_none()
        if kb is None:
            kb = kb_service.create_kb(
                session, name="设备知识库", description="合成技术文档", created_by=admin.id
            )
            created["kb"] = 1
        kb_service.bind_application(session, app.id, kb.id)

        existing_grant = session.execute(
            select(ResourceGrant).where(
                ResourceGrant.user_id == admin.id,
                ResourceGrant.resource_type == "KNOWLEDGE_BASE",
                ResourceGrant.resource_id == kb.id,
            )
        ).scalar_one_or_none()
        if existing_grant is None:
            auth_service.grant_resource(
                session,
                user_id=admin.id,
                resource_type="KNOWLEDGE_BASE",
                resource_id=kb.id,
                permission="READ",
            )
            created["grant"] = 1

        for name, text in KB_DOCS.items():
            path = rag_service.UPLOAD_ROOT / f"seed_{name}"
            rag_service.UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            document = kb_service.add_document_metadata(
                session, kb_id=kb.id, title=name, filename=name, content_type="text/markdown"
            )
            rag_service.ingest_document(session, document, path)
            created[f"doc:{name}"] = document.status

        published = app.status
        if app.status != "PUBLISHED":
            app_service.publish(session, app, published_by=admin.id)
            published = "PUBLISHED"

    engine.dispose()
    print("created:", created)
    print("login: admin /", PASSWORD)
    print("app slug: /apps/service-agent ; published:", published)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())