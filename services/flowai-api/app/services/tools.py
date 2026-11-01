"""工具注册表服务：白名单登记、Schema 校验、应用授权（M04-01；docs/05 §3）。"""

from typing import Any

import jsonschema
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import AIApplication, ApplicationTool, ToolDefinition

# 预置工具（P0 最少 5 个，docs/05 §3）
PRESET_TOOLS: list[dict[str, Any]] = [
    {
        "tool_code": "get_device_info",
        "name": "查询设备信息",
        "kind": "READ",
        "description": "按设备 ID 获取设备型号、客户、保修与状态",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "integer", "minimum": 1}},
            "required": ["device_id"],
            "additionalProperties": False,
        },
    },
    {
        "tool_code": "get_device_faults",
        "name": "查询设备故障",
        "kind": "READ",
        "description": "查询指定设备的历史故障记录",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "integer", "minimum": 1},
                "severity": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
            },
            "required": ["device_id"],
            "additionalProperties": False,
        },
    },
    {
        "tool_code": "get_device_tickets",
        "name": "查询设备工单",
        "kind": "READ",
        "description": "查询指定设备的维修工单列表",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "integer", "minimum": 1},
                "status": {
                    "type": "string",
                    "enum": ["PENDING", "IN_PROGRESS", "RESOLVED", "CLOSED", "REOPENED"],
                },
            },
            "required": ["device_id"],
            "additionalProperties": False,
        },
    },
    {
        "tool_code": "get_ticket_status",
        "name": "查询工单状态",
        "kind": "READ",
        "description": "按工单 ID 查询状态、版本与时间线",
        "input_schema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "integer", "minimum": 1}},
            "required": ["ticket_id"],
            "additionalProperties": False,
        },
    },
    {
        "tool_code": "search_technical_docs",
        "name": "检索技术文档",
        "kind": "READ",
        "description": "在应用绑定的知识库内检索，返回带引用的证据",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 500},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "tool_code": "create_repair_ticket",
        "name": "创建维修工单",
        "kind": "WRITE",
        "description": "预检查并创建维修工单（必须人工确认 + 重复风险二次确认 + 幂等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "integer", "minimum": 1},
                "fault_id": {"type": ["integer", "null"], "minimum": 1},
                "reported_fault_code": {"type": ["string", "null"], "maxLength": 40},
                "title": {"type": "string", "minLength": 1, "maxLength": 150},
                "description": {"type": "string", "minLength": 1},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "URGENT"]},
            },
            "required": ["device_id", "title", "description"],
            "additionalProperties": False,
        },
    },
]


def seed_tools(session: Session) -> dict[str, int]:
    created = 0
    for spec in PRESET_TOOLS:
        existing = session.execute(
            select(ToolDefinition).where(ToolDefinition.tool_code == spec["tool_code"])
        ).scalar_one_or_none()
        if existing is not None:
            existing.name = spec["name"]
            existing.description = spec["description"]
            existing.kind = spec["kind"]
            existing.input_schema = spec["input_schema"]
            continue
        session.add(
            ToolDefinition(
                tool_code=spec["tool_code"],
                name=spec["name"],
                description=spec["description"],
                kind=spec["kind"],
                input_schema=spec["input_schema"],
                is_enabled=True,
            )
        )
        created += 1
    session.commit()
    return {"created": created, "total": len(PRESET_TOOLS)}


def list_tools(session: Session) -> list[ToolDefinition]:
    return (
        session.execute(select(ToolDefinition).order_by(ToolDefinition.id)).scalars().all()
    )


def get_tool(session: Session, tool_code: str) -> ToolDefinition:
    tool = session.execute(
        select(ToolDefinition).where(ToolDefinition.tool_code == tool_code)
    ).scalar_one_or_none()
    if tool is None:
        raise ApiError(404, "TOOL_NOT_FOUND", "工具不存在")
    if not tool.is_enabled:
        raise ApiError(422, "TOOL_DISABLED", "工具已停用")
    return tool


def bind_tool(session: Session, application_id: int, tool_code: str) -> ApplicationTool:
    if session.get(AIApplication, application_id) is None:
        raise ApiError(404, "APPLICATION_NOT_FOUND", "应用不存在")
    tool = get_tool(session, tool_code)
    existing = session.execute(
        select(ApplicationTool).where(
            ApplicationTool.application_id == application_id,
            ApplicationTool.tool_id == tool.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    link = ApplicationTool(application_id=application_id, tool_id=tool.id)
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def unbind_tool(session: Session, application_id: int, tool_code: str) -> bool:
    tool = get_tool(session, tool_code)
    link = session.execute(
        select(ApplicationTool).where(
            ApplicationTool.application_id == application_id,
            ApplicationTool.tool_id == tool.id,
        )
    ).scalar_one_or_none()
    if link is None:
        return False
    session.delete(link)
    session.commit()
    return True


def application_tools(session: Session, application_id: int) -> list[ToolDefinition]:
    rows = session.execute(
        select(ToolDefinition)
        .join(ApplicationTool, ApplicationTool.tool_id == ToolDefinition.id)
        .where(ApplicationTool.application_id == application_id)
        .order_by(ToolDefinition.id)
    ).scalars()
    return list(rows.all())


def authorized_tool(session: Session, application_id: int, tool_code: str) -> ToolDefinition:
    """只允许应用已授权且启用的白名单工具（拒绝任意 URL/SQL/shell）。"""
    tool = get_tool(session, tool_code)
    bound = session.execute(
        select(ApplicationTool).where(
            ApplicationTool.application_id == application_id,
            ApplicationTool.tool_id == tool.id,
        )
    ).scalar_one_or_none()
    if bound is None:
        raise ApiError(403, "TOOL_NOT_AUTHORIZED", "该应用未授权此工具")
    return tool


def validate_arguments(tool: ToolDefinition, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        jsonschema.validate(instance=arguments, schema=tool.input_schema)
    except jsonschema.ValidationError as exc:
        raise ApiError(
            400,
            "TOOL_ARGUMENT_INVALID",
            "工具参数校验失败",
            {"field": list(exc.absolute_path), "reason": exc.message},
        ) from exc
    return arguments