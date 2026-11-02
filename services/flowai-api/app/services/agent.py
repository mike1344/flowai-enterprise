"""Agent 编排（M04-03/04）：读工具 → 草稿 → 人工确认 → 重复确认 → 幂等创建。

状态机（docs/05 §4）：
RUNNING → WAITING_CONFIRMATION → RUNNING → WAITING_DUPLICATE_CONFIRMATION → RUNNING → SUCCEEDED
异常 → FAILED / TIMED_OUT；用户拒绝 → CANCELLED。
"""

import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.base import utcnow
from app.models import (
    AgentExecution,
    AIApplication,
    ApplicationKnowledgeBase,
    Conversation,
    Message,
    OperationConfirmation,
    ResourceGrant,
)
from app.services import rag as rag_service
from app.services.connector import ConnectorError, ConnectorTimeout, IndustrialConnector, record_tool

CONFIRM_TTL_SECONDS = 300
WRITE_KEYWORDS = ("创建工单", "报修", "维修申请", "申请维修", "帮我建单", "开单", "需要开单")


def params_digest(payload: dict[str, Any]) -> str:
    import json

    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def detect_intent(message: str) -> dict[str, Any]:
    device_match = re.search(r"(HC\d{3}|SC\d{3}|DEV-[A-Za-z0-9-]+)", message, re.IGNORECASE)
    id_match = re.search(r"(?:device_id|设备\s*id)\s*[:：=]?\s*(\d+)", message, re.IGNORECASE)
    wants_write = any(keyword in message for keyword in WRITE_KEYWORDS)
    return {
        "device_code": device_match.group(1) if device_match else None,
        "device_id": int(id_match.group(1)) if id_match else None,
        "wants_write": wants_write,
        "raw": message,
    }


def resolve_device(connector: IndustrialConnector, intent: dict, *, subject: str, role: str, trace_id: str | None):
    device_id = intent.get("device_id")
    if device_id:
        return connector.get(f"/devices/{device_id}", subject=subject, role=role, trace_id=trace_id)
    return None


def _app_kb_ids(session: Session, application_id: int) -> list[int]:
    rows = session.execute(
        select(ApplicationKnowledgeBase.knowledge_base_id).where(
            ApplicationKnowledgeBase.application_id == application_id
        )
    ).scalars()
    return sorted(rows.all())


def _granted(session: Session, user_id: int) -> set[int]:
    rows = session.execute(
        select(ResourceGrant.resource_id).where(
            ResourceGrant.user_id == user_id,
            ResourceGrant.resource_type == "KNOWLEDGE_BASE",
        )
    ).scalars()
    return set(rows.all())


def start_execution(
    session: Session,
    *,
    settings: Settings,
    conversation: Conversation,
    user_message: str,
    subject: str,
    role: str,
    trace_id: str | None,
    transport=None,
    llm_transport=None,
) -> dict[str, Any]:
    app = session.get(AIApplication, conversation.application_id)
    if app is None or app.status != "PUBLISHED":
        raise ApiError(404, "APPLICATION_NOT_PUBLISHED", "应用未发布，不能对话")

    session.add(
        Message(conversation_id=conversation.id, role="USER", content=user_message)
    )
    execution = AgentExecution(
        conversation_id=conversation.id,
        application_id=app.id,
        user_id=conversation.user_id,
        status="RUNNING",
        intent=None,
        trace_id=trace_id,
    )
    session.add(execution)
    session.flush()

    intent = detect_intent(user_message)
    execution.intent = intent
    session.flush()

    connector = IndustrialConnector(settings, transport=transport)
    answer_parts: list[str] = []
    citations: list[dict] = []
    device: dict | None = None

    try:
        device = resolve_device(connector, intent, subject=subject, role=role, trace_id=trace_id)
        if device:
            record_tool(
                session, execution,
                tool_code="get_device_info",
                arguments={"device_id": device["id"]},
                status="SUCCEEDED", result=device, latency_ms=0, trace_id=trace_id,
            )
            answer_parts.append(
                f"设备 {device['device_code']}（客户 {device.get('customer_name') or device['customer_id']}，"
                f"状态 {device['status']}）"
            )
            faults = connector.get(
                f"/devices/{device['id']}/faults",
                subject=subject, role=role, trace_id=trace_id,
            )
            record_tool(
                session, execution,
                tool_code="get_device_faults",
                arguments={"device_id": device["id"]},
                status="SUCCEEDED", result=faults, latency_ms=0, trace_id=trace_id,
            )
            if faults.get("items"):
                answer_parts.append(f"历史故障 {faults['total']} 条，最近：{faults['items'][0]['title']}")
            tickets = connector.get(
                f"/devices/{device['id']}/tickets",
                subject=subject, role=role, trace_id=trace_id,
            )
            record_tool(
                session, execution,
                tool_code="get_device_tickets",
                arguments={"device_id": device["id"]},
                status="SUCCEEDED", result=tickets, latency_ms=0, trace_id=trace_id,
            )
            if tickets.get("items"):
                answer_parts.append(f"未关闭工单 {tickets['total']} 条")
        else:
            answer_parts.append("未识别到设备编号（例如 HC200/DEV-xxx 或 device_id: 12）。")
    except ConnectorTimeout as exc:
        execution.status = "TIMED_OUT"
        execution.error_code = exc.code
        execution.error_message = exc.message
        session.flush()
        _append_assistant(session, conversation.id, f"{exc.message}。请稍后在工单列表中核实。", [], execution.id)
        connector.close()
        session.commit()
        return {"execution_id": execution.id, "status": execution.status, "message": exc.message}
    except ConnectorError as exc:
        execution.status = "FAILED"
        execution.error_code = exc.code
        execution.error_message = exc.message
        session.flush()
        _append_assistant(session, conversation.id, f"调用工业服务失败：{exc.message}", [], execution.id)
        connector.close()
        session.commit()
        return {"execution_id": execution.id, "status": execution.status, "message": exc.message}

    # 知识库检索（只读，带引用）
    if app.id and set(_app_kb_ids(session, app.id)) & _granted(session, conversation.user_id):
        search = rag_service.answer_with_evidence(
            session,
            application_id=app.id,
            user_id=conversation.user_id,
            query=user_message,
            settings=settings,
        )
        record_tool(
            session, execution,
            tool_code="search_technical_docs",
            arguments={"query": user_message},
            status="SUCCEEDED", result={"refused": search["refused"]}, latency_ms=0, trace_id=trace_id,
        )
        citations = search.get("citations", [])
        if not search["refused"]:
            answer_parts.append(search["answer"])

    # 真实模型回答（有依据时才调用；失败回退到确定性回答，不静默编造）
    answer_parts = _compose_with_llm(
        session,
        app=app,
        execution=execution,
        user_message=user_message,
        answer_parts=answer_parts,
        citations=citations,
        has_evidence=bool(device) or bool(citations),
        transport=llm_transport,
    )

    # 写操作意图 → 生成草稿并要求人工确认（未确认不得写）
    if intent["wants_write"] and device:
        draft = {
            "device_id": device["id"],
            "title": f"{device['device_code']} 故障维修",
            "description": user_message,
            "priority": "NORMAL",
            "reported_fault_code": None,
            "fault_id": None,
        }
        execution.draft_operation = draft
        execution.idempotency_key = f"agent-{execution.id}-{secrets.token_hex(8)}"
        token = secrets.token_urlsafe(24)
        session.add(
            OperationConfirmation(
                execution_id=execution.id,
                user_id=conversation.user_id,
                operation="create_repair_ticket",
                params_digest=params_digest(draft),
                token_hash=hash_token(token),
                expires_at=utcnow() + timedelta(seconds=CONFIRM_TTL_SECONDS),
            )
        )
        execution.status = "WAITING_CONFIRMATION"
        session.flush()
        answer_parts.append("以上为工单草稿，请确认后再提交创建。")
        message = _append_assistant(
            session, conversation.id, "\n".join(answer_parts), citations, execution.id
        )
        connector.close()
        session.commit()
        return {
            "execution_id": execution.id,
            "status": execution.status,
            "message": message.content,
            "citations": citations,
            "draft": draft,
            "confirmation_token": token,
            "expires_in_seconds": CONFIRM_TTL_SECONDS,
        }

    execution.status = "SUCCEEDED"
    session.flush()
    message = _append_assistant(session, conversation.id, "\n".join(answer_parts), citations, execution.id)
    connector.close()
    session.commit()
    return {
        "execution_id": execution.id,
        "status": execution.status,
        "message": message.content,
        "citations": citations,
    }


def _append_assistant(
    session: Session, conversation_id: int, content: str, citations: list, execution_id: int
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role="ASSISTANT",
        content=content,
        citations=citations,
        execution_id=execution_id,
    )
    session.add(message)
    session.flush()
    return message


def _load_confirmation(session: Session, execution: AgentExecution, token: str) -> OperationConfirmation:
    record = session.execute(
        select(OperationConfirmation).where(
            OperationConfirmation.execution_id == execution.id,
            OperationConfirmation.token_hash == hash_token(token),
        )
    ).scalar_one_or_none()
    if record is None:
        raise ApiError(403, "CONFIRMATION_INVALID", "确认无效")
    if record.consumed_at is not None:
        raise ApiError(409, "CONFIRMATION_ALREADY_USED", "确认已被使用")
    if record.expires_at <= utcnow():
        raise ApiError(409, "CONFIRMATION_EXPIRED", "确认已过期，请重新发起")
    if execution.draft_operation and record.params_digest != params_digest(execution.draft_operation):
        raise ApiError(409, "CONFIRMATION_PARAMS_CHANGED", "操作参数已变化，请重新确认")
    return record


def confirm_operation(
    session: Session,
    *,
    settings: Settings,
    execution: AgentExecution,
    token: str,
    subject: str,
    role: str,
    trace_id: str | None,
    transport=None,
    llm_transport=None,
) -> dict[str, Any]:
    if execution.status != "WAITING_CONFIRMATION":
        raise ApiError(409, "EXECUTION_NOT_WAITING", "该执行不在待确认状态")

    record = _load_confirmation(session, execution, token)
    draft = execution.draft_operation or {}
    connector = IndustrialConnector(settings, transport=transport)
    started = time.perf_counter()
    try:
        precheck = connector.post(
            "/tickets/precheck",
            subject=subject, role=role, trace_id=trace_id, json_body=draft,
        )
    except ConnectorTimeout:
        execution.status = "TIMED_OUT"
        execution.error_code = "PRECHECK_TIMEOUT"
        execution.error_message = "预检查超时，结果待核实"
        session.flush()
        connector.close()
        session.commit()
        return {"execution_id": execution.id, "status": execution.status, "message": "预检查超时，结果待核实"}
    except ConnectorError as exc:
        execution.status = "FAILED"
        execution.error_code = exc.code
        execution.error_message = exc.message
        session.flush()
        connector.close()
        session.commit()
        return {"execution_id": execution.id, "status": execution.status, "message": exc.message}

    record_tool(
        session, execution,
        tool_code="create_repair_ticket.precheck",
        arguments=draft, status="SUCCEEDED", result=precheck,
        latency_ms=int((time.perf_counter() - started) * 1000), trace_id=trace_id,
    )

    if precheck.get("risk_level") == "HIGH":
        execution.status = "WAITING_DUPLICATE_CONFIRMATION"
        execution.result = {"existing_tickets": precheck.get("existing_tickets", [])}
        session.flush()
        connector.close()
        session.commit()
        return {
            "execution_id": execution.id,
            "status": execution.status,
            "message": "发现疑似重复的未关闭工单，是否仍要创建？",
            "existing_tickets": precheck.get("existing_tickets", []),
            "duplicate_confirmation_token": precheck.get("confirmation_token"),
            "expires_in_seconds": precheck.get("expires_in_seconds"),
        }

    return _create_ticket(
        session,
        settings=settings,
        execution=execution,
        connector=connector,
        draft=draft,
        confirmation_record=record,
        duplicate_token=None,
        subject=subject,
        role=role,
        trace_id=trace_id,
    )


def confirm_duplicate(
    session: Session,
    *,
    settings: Settings,
    execution: AgentExecution,
    duplicate_token: str,
    subject: str,
    role: str,
    trace_id: str | None,
    transport=None,
    llm_transport=None,
) -> dict[str, Any]:
    if execution.status != "WAITING_DUPLICATE_CONFIRMATION":
        raise ApiError(409, "EXECUTION_NOT_WAITING", "该执行不在待重复确认状态")
    draft = execution.draft_operation or {}
    connector = IndustrialConnector(settings, transport=transport)
    return _create_ticket(
        session,
        settings=settings,
        execution=execution,
        connector=connector,
        draft=draft,
        confirmation_record=None,
        duplicate_token=duplicate_token,
        subject=subject,
        role=role,
        trace_id=trace_id,
    )


def _create_ticket(
    session: Session,
    *,
    settings: Settings,
    execution: AgentExecution,
    connector: IndustrialConnector,
    draft: dict,
    confirmation_record: OperationConfirmation | None,
    duplicate_token: str | None,
    subject: str,
    role: str,
    trace_id: str | None,
) -> dict[str, Any]:
    body = dict(draft)
    if duplicate_token:
        body["confirmation_token"] = duplicate_token
    started = time.perf_counter()
    try:
        created = connector.post(
            "/tickets",
            subject=subject, role=role, trace_id=trace_id, json_body=body,
            headers={"Idempotency-Key": execution.idempotency_key or f"exec-{execution.id}"},
        )
    except ConnectorTimeout:
        # 结果未知：不得报成功，保留幂等键以便安全重试
        execution.status = "TIMED_OUT"
        execution.error_code = "TICKET_CREATE_TIMEOUT"
        execution.error_message = "创建工单超时，结果待核实（可用同一幂等键重试）"
        session.flush()
        connector.close()
        session.commit()
        return {"execution_id": execution.id, "status": execution.status, "message": execution.error_message}
    except ConnectorError as exc:
        if exc.code == "DUPLICATE_TICKET_CONFIRMATION_REQUIRED":
            execution.status = "WAITING_DUPLICATE_CONFIRMATION"
            execution.result = {"existing_tickets": (exc.details or {}).get("existing_tickets", [])}
            session.flush()
            connector.close()
            session.commit()
            return {
                "execution_id": execution.id,
                "status": execution.status,
                "message": "发现疑似重复工单，需二次确认",
                "duplicate_confirmation_token": (exc.details or {}).get("confirmation_token"),
            }
        execution.status = "FAILED"
        execution.error_code = exc.code
        execution.error_message = exc.message
        session.flush()
        connector.close()
        session.commit()
        return {"execution_id": execution.id, "status": execution.status, "message": exc.message}

    record_tool(
        session, execution,
        tool_code="create_repair_ticket",
        arguments=body, status="SUCCEEDED", result=created,
        latency_ms=int((time.perf_counter() - started) * 1000), trace_id=trace_id,
    )
    if confirmation_record is not None:
        confirmation_record.consumed_at = utcnow()
    execution.status = "SUCCEEDED"
    execution.result = created
    session.flush()
    _append_assistant(
        session,
        execution.conversation_id,
        f"工单已创建：{created.get('ticket_no')}（状态 {created.get('status')}）。",
        [],
        execution.id,
    )
    connector.close()
    session.commit()
    return {
        "execution_id": execution.id,
        "status": execution.status,
        "ticket_no": created.get("ticket_no"),
        "ticket_status": created.get("status"),
        "message": f"工单已创建：{created.get('ticket_no')}",
    }


def cancel_execution(session: Session, execution: AgentExecution) -> dict[str, Any]:
    if execution.status in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}:
        raise ApiError(409, "EXECUTION_FINISHED", "该执行已结束")
    execution.status = "CANCELLED"
    session.flush()
    _append_assistant(session, execution.conversation_id, "已取消该操作，未写入任何业务数据。", [], execution.id)
    session.commit()
    return {"execution_id": execution.id, "status": execution.status}
def retry_operation(
    session: Session,
    *,
    settings: Settings,
    execution: AgentExecution,
    subject: str,
    role: str,
    trace_id: str | None,
    transport=None,
    llm_transport=None,
) -> dict[str, Any]:
    """P1：失败/超时后按同一幂等键安全重试；不会产生重复工单。"""
    if execution.status == "SUCCEEDED":
        raise ApiError(409, "EXECUTION_ALREADY_SUCCEEDED", "该执行已成功，无需重试")
    if execution.status not in {"FAILED", "TIMED_OUT"}:
        raise ApiError(409, "EXECUTION_NOT_RETRYABLE", "当前状态不可重试")
    if not execution.idempotency_key or not execution.draft_operation:
        raise ApiError(422, "EXECUTION_NOT_RETRYABLE", "缺少幂等键或操作草稿，无法安全重试")

    connector = IndustrialConnector(settings, transport=transport)
    return _create_ticket(
        session,
        settings=settings,
        execution=execution,
        connector=connector,
        draft=execution.draft_operation,
        confirmation_record=None,
        duplicate_token=None,
        subject=subject,
        role=role,
        trace_id=trace_id,
    )
def _app_model_config(session: Session, app: AIApplication):
    """取当前发布版本的模型配置；未发布则用草稿配置。"""
    from app.models import ApplicationVersion, ModelConfig

    config = app.draft_config or {}
    if app.current_version_id:
        version = session.get(ApplicationVersion, app.current_version_id)
        if version is not None:
            config = version.config or config
    model_id = config.get("model_config_id")
    if not model_id:
        return None
    return session.get(ModelConfig, int(model_id))


def _compose_with_llm(
    session: Session,
    *,
    app: AIApplication,
    execution: AgentExecution,
    user_message: str,
    answer_parts: list[str],
    citations: list[dict],
    has_evidence: bool,
    transport=None,
) -> list[str]:
    """调用真实模型润色/组织回答；无依据不调用；失败回退并记录原因。"""
    from app.services import llm

    config = _app_model_config(session, app)
    if config is None or config.provider == "MOCK":
        return answer_parts
    if not has_evidence:
        return answer_parts  # 无证据时不调用模型，保持明确拒答语义

    context_lines = list(answer_parts)
    for citation in citations[:5]:
        context_lines.append(
            f"- 引用《{citation.get('document_title')}》（{citation.get('page_label')}）：{citation.get('snippet', '')[:160]}"
        )
    context = "\n".join(context_lines) or "（无）"

    system_prompt = (app.draft_config or {}).get("system_prompt") or ""
    messages = llm.build_messages(system_prompt=system_prompt, context=context, question=user_message)

    try:
        result = llm.chat(
            config,
            messages,
            transport=transport,
            timeout=float(getattr(config, "_llm_timeout", 30.0)),
        )
    except llm.LlmError as exc:
        execution.result = {
            **(execution.result or {}),
            "llm": {"status": "fallback", "code": exc.code, "message": exc.message},
        }
        return answer_parts

    execution.prompt_tokens = result.prompt_tokens
    execution.completion_tokens = result.completion_tokens
    execution.llm_model = result.model
    execution.result = {
        **(execution.result or {}),
        "llm": {"status": "used", **result.as_usage()},
    }
    return [result.content]