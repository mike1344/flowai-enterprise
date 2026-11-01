"""工具注册表与应用授权接口（M04-01）。"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_permission, verify_csrf
from app.core.errors import ApiError, ok
from app.models import ToolDefinition
from app.services import tools as tool_service

router = APIRouter()


class InvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)


def serialize(tool: ToolDefinition, bound: bool = False) -> dict[str, Any]:
    return {
        "tool_code": tool.tool_code,
        "name": tool.name,
        "kind": tool.kind,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "is_enabled": tool.is_enabled,
        "authorized": bound,
    }


@router.get("/tools")
async def list_tools(
    current: CurrentUser = Depends(require_permission("tool:manage")),
    session: Session = Depends(get_db),
) -> dict:
    rows = tool_service.list_tools(session)
    return ok({"items": [serialize(row) for row in rows], "total": len(rows)}, "工具注册表")


@router.get("/applications/{application_id}/tools")
async def list_application_tools(
    application_id: int,
    current: CurrentUser = Depends(require_permission("app:manage")),
    session: Session = Depends(get_db),
) -> dict:
    rows = tool_service.application_tools(session, application_id)
    return ok({"items": [serialize(row, bound=True) for row in rows]}, "应用已授权工具")


@router.post("/applications/{application_id}/tools/{tool_code}")
async def bind_tool(
    application_id: int,
    tool_code: str,
    current: CurrentUser = Depends(require_permission("tool:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    tool = tool_service.bind_tool(session, application_id, tool_code)
    return ok({"application_id": application_id, "tool_code": tool_code, "tool_id": tool.id}, "工具已授权")


@router.delete("/applications/{application_id}/tools/{tool_code}")
async def unbind_tool(
    application_id: int,
    tool_code: str,
    current: CurrentUser = Depends(require_permission("tool:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    removed = tool_service.unbind_tool(session, application_id, tool_code)
    if not removed:
        raise ApiError(404, "TOOL_BINDING_NOT_FOUND", "工具授权不存在")
    return ok({"removed": True}, "工具授权已解除")


@router.post("/applications/{application_id}/tools/{tool_code}/validate")
async def validate_tool_arguments(
    application_id: int,
    tool_code: str,
    payload: InvokeRequest,
    current: CurrentUser = Depends(require_permission("app:manage")),
    session: Session = Depends(get_db),
) -> dict:
    tool = tool_service.authorized_tool(session, application_id, tool_code)
    tool_service.validate_arguments(tool, payload.arguments)
    return ok({"tool_code": tool_code, "valid": True, "kind": tool.kind}, "参数校验通过")