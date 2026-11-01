"""会话、消息与 Agent 执行接口（M04-03/04）。"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db, verify_csrf
from app.core.errors import ApiError, ok
from app.models import (
    AIApplication,
    AgentExecution,
    Conversation,
    Message,
    ResourceGrant,
)
from app.services import agent as agent_service

router = APIRouter()


class _Strict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MessageCreate(_Strict):
    content: str = Field(min_length=1, max_length=4000)


class ConfirmRequest(_Strict):
    token: str = Field(min_length=8, max_length=200)


class DuplicateConfirmRequest(_Strict):
    token: str = Field(min_length=8, max_length=400)


def _can_use_app(session: Session, current: CurrentUser, app: AIApplication) -> bool:
    if current.has("app:manage"):
        return True
    grant = session.execute(
        select(ResourceGrant.id).where(
            ResourceGrant.user_id == current.user.id,
            ResourceGrant.resource_type == "APPLICATION",
            ResourceGrant.resource_id == app.id,
            ResourceGrant.permission.in_(("USE", "READ", "MANAGE")),
        )
    ).scalar_one_or_none()
    return grant is not None


def _published_app_by_slug(session: Session, slug: str) -> AIApplication:
    app = session.execute(
        select(AIApplication).where(AIApplication.slug == slug.lower())
    ).scalar_one_or_none()
    if app is None or app.status != "PUBLISHED":
        raise ApiError(404, "APPLICATION_NOT_FOUND", "应用不存在或未发布")
    return app


def industrial_role(current: CurrentUser) -> str:
    if "PLATFORM_ADMIN" in current.roles or "SERVICE_ADMIN" in current.roles:
        return "SERVICE_ADMIN"
    if "BUSINESS_USER" in current.roles or "APP_ADMIN" in current.roles:
        return "SERVICE_STAFF"
    return "CUSTOMER_USER"


@router.post("/apps/{slug}/sessions", status_code=201)
async def create_session(
    slug: str,
    current: CurrentUser = Depends(get_current_user),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    app = _published_app_by_slug(session, slug)
    if not _can_use_app(session, current, app):
        raise ApiError(403, "PERMISSION_DENIED", "你没有该应用的使用授权")

    conversation = Conversation(
        application_id=app.id,
        app_version_id=app.current_version_id,
        user_id=current.user.id,
        status="ACTIVE",
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return ok(
        {
            "conversation_id": conversation.id,
            "application_id": app.id,
            "app_version_id": conversation.app_version_id,
        },
        "会话已创建",
    )


@router.get("/sessions/{conversation_id}/messages")
async def list_messages(
    conversation_id: int,
    current: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != current.user.id:
        raise ApiError(404, "CONVERSATION_NOT_FOUND", "会话不存在")
    rows = session.execute(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id)
    ).scalars()
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "role": row.role,
                    "content": row.content,
                    "citations": row.citations or [],
                    "execution_id": row.execution_id,
                }
                for row in rows
            ]
        },
        "会话消息",
    )


@router.post("/sessions/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    payload: MessageCreate,
    request: Request,
    current: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != current.user.id:
        raise ApiError(404, "CONVERSATION_NOT_FOUND", "会话不存在")

    result = agent_service.start_execution(
        session,
        settings=request.app.state.settings,
        conversation=conversation,
        user_message=payload.content,
        subject=current.user.username,
        role=industrial_role(current),
        trace_id=getattr(request.state, "trace_id", None),
        transport=getattr(request.app.state, "connector_transport", None),
    )
    return ok(result, "执行完成" if result["status"] == "SUCCEEDED" else "等待确认")


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: int,
    current: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    execution = session.get(AgentExecution, execution_id)
    if execution is None or execution.user_id != current.user.id:
        raise ApiError(404, "EXECUTION_NOT_FOUND", "执行不存在")
    return ok(
        {
            "id": execution.id,
            "status": execution.status,
            "intent": execution.intent,
            "draft": execution.draft_operation,
            "result": execution.result,
            "error_code": execution.error_code,
            "error_message": execution.error_message,
            "trace_id": execution.trace_id,
        },
        "执行详情",
    )


@router.post("/executions/{execution_id}/confirm")
async def confirm_execution(
    execution_id: int,
    payload: ConfirmRequest,
    request: Request,
    current: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    execution = session.get(AgentExecution, execution_id)
    if execution is None or execution.user_id != current.user.id:
        raise ApiError(404, "EXECUTION_NOT_FOUND", "执行不存在")
    result = agent_service.confirm_operation(
        session,
        settings=request.app.state.settings,
        execution=execution,
        token=payload.token,
        subject=current.user.username,
        role=industrial_role(current),
        trace_id=getattr(request.state, "trace_id", None),
        transport=getattr(request.app.state, "connector_transport", None),
    )
    return ok(result, "已提交" if result["status"] == "SUCCEEDED" else "等待二次确认")


@router.post("/executions/{execution_id}/confirm-duplicate")
async def confirm_duplicate(
    execution_id: int,
    payload: DuplicateConfirmRequest,
    request: Request,
    current: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    execution = session.get(AgentExecution, execution_id)
    if execution is None or execution.user_id != current.user.id:
        raise ApiError(404, "EXECUTION_NOT_FOUND", "执行不存在")
    result = agent_service.confirm_duplicate(
        session,
        settings=request.app.state.settings,
        execution=execution,
        duplicate_token=payload.token,
        subject=current.user.username,
        role=industrial_role(current),
        trace_id=getattr(request.state, "trace_id", None),
        transport=getattr(request.app.state, "connector_transport", None),
    )
    return ok(result, "已提交")


@router.post("/executions/{execution_id}/reject")
async def reject_execution(
    execution_id: int,
    current: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    execution = session.get(AgentExecution, execution_id)
    if execution is None or execution.user_id != current.user.id:
        raise ApiError(404, "EXECUTION_NOT_FOUND", "执行不存在")
    return ok(agent_service.cancel_execution(session, execution), "已取消")
@router.get("/executions/{execution_id}/steps")
async def execution_steps(
    execution_id: int,
    current: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    """P1：执行可视化——只暴露结构化步骤，不暴露模型内部推理链。"""
    from sqlalchemy import select as _select

    from app.models import ToolExecution

    execution = session.get(AgentExecution, execution_id)
    if execution is None or execution.user_id != current.user.id:
        raise ApiError(404, "EXECUTION_NOT_FOUND", "执行不存在")

    steps = session.execute(
        _select(ToolExecution)
        .where(ToolExecution.execution_id == execution.id)
        .order_by(ToolExecution.id)
    ).scalars()
    return ok(
        {
            "execution_id": execution.id,
            "status": execution.status,
            "error_code": execution.error_code,
            "steps": [
                {
                    "step": index + 1,
                    "tool_code": row.tool_code,
                    "status": row.status,
                    "latency_ms": row.latency_ms,
                    "trace_id": row.trace_id,
                    "created_at": row.created_at.isoformat(),
                }
                for index, row in enumerate(steps)
            ],
        },
        "执行步骤",
    )


@router.post("/executions/{execution_id}/retry")
async def retry_execution(
    execution_id: int,
    request: Request,
    current: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    """P1：失败/超时的安全重试——复用同一幂等键，已成功则不再写入。"""
    execution = session.get(AgentExecution, execution_id)
    if execution is None or execution.user_id != current.user.id:
        raise ApiError(404, "EXECUTION_NOT_FOUND", "执行不存在")
    if execution.status == "SUCCEEDED":
        raise ApiError(409, "EXECUTION_ALREADY_SUCCEEDED", "该执行已成功，无需重试")
    if execution.status not in {"FAILED", "TIMED_OUT"}:
        raise ApiError(409, "EXECUTION_NOT_RETRYABLE", "当前状态不可重试")

    if not execution.idempotency_key or not execution.draft_operation:
        raise ApiError(422, "EXECUTION_NOT_RETRYABLE", "缺少幂等键或操作草稿，无法安全重试")

    result = agent_service.retry_operation(
        session,
        settings=request.app.state.settings,
        execution=execution,
        subject=current.user.username,
        role=industrial_role(current),
        trace_id=getattr(request.state, "trace_id", None),
        transport=getattr(request.app.state, "connector_transport", None),
    )
    return ok(result, "已按同一幂等键重试")