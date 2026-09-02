"""Inbound HTTP routes for the existing migration MVP."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agent.orchestrator import AgentServiceError, ask_agent, stream_agent_events
from app.container import AppContainer
from app.integrations.ollama import OllamaGatewayError
from app.mcp.gateway import McpGatewayError, call_current_datetime

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
router = APIRouter()


class AgentAskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message 不能为空")
        return normalized


def _sse_data(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def _stream_agent_response(
    message: str,
    container: AppContainer,
) -> AsyncIterator[str]:
    try:
        async for event in stream_agent_events(
            message,
            container.mcp_gateway_factory,
            container.ollama_gateway_factory,
        ):
            yield _sse_data(event)
    except asyncio.CancelledError:
        logger.debug("Agent SSE 请求被客户端取消")
        raise
    except (AgentServiceError, McpGatewayError, OllamaGatewayError) as exc:
        logger.warning("Agent SSE 调用失败，阶段=%s，原因=%s", exc.stage, exc.message)
        yield _sse_data(
            {
                "type": "error",
                "stage": exc.stage,
                "content": exc.message,
            }
        )
    except Exception:
        logger.exception("Agent SSE 调用发生未处理异常")
        yield _sse_data(
            {
                "type": "error",
                "stage": "unexpected",
                "content": "AIHost 发生未预期错误",
            }
        )

    yield "data: [DONE]\n\n"


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/mvp")


@router.get("/mvp", include_in_schema=False)
async def mvp_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/static/app.js", include_in_schema=False)
async def mvp_script() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js", media_type="text/javascript")


@router.get("/static/styles.css", include_in_schema=False)
async def mvp_styles() -> FileResponse:
    return FileResponse(STATIC_DIR / "styles.css", media_type="text/css")


@router.post("/api/mvp/tools/get_current_date_time/call")
async def call_datetime_tool() -> JSONResponse:
    try:
        payload = await call_current_datetime()
        return JSONResponse(status_code=200, content=payload)
    except McpGatewayError as exc:
        logger.warning("MCP MVP 调用失败，阶段=%s，原因=%s", exc.stage, exc.message)
        return JSONResponse(
            status_code=502,
            content={"success": False, "stage": exc.stage, "message": exc.message},
        )
    except Exception:
        logger.exception("MCP MVP 调用发生未处理异常")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "stage": "unexpected",
                "message": "AIHost 发生未预期错误",
            },
        )


@router.post("/api/mvp/agent/ask")
async def ask_with_ollama(request: AgentAskRequest, http_request: Request) -> JSONResponse:
    try:
        container: AppContainer = http_request.app.state.container
        payload = await ask_agent(
            request.message,
            container.mcp_gateway_factory,
            container.ollama_gateway_factory,
        )
        return JSONResponse(status_code=200, content=payload)
    except (AgentServiceError, McpGatewayError, OllamaGatewayError) as exc:
        logger.warning("Agent MVP 调用失败，阶段=%s，原因=%s", exc.stage, exc.message)
        return JSONResponse(
            status_code=502,
            content={"success": False, "stage": exc.stage, "message": exc.message},
        )
    except Exception:
        logger.exception("Agent MVP 调用发生未处理异常")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "stage": "unexpected",
                "message": "AIHost 发生未预期错误",
            },
        )


@router.post("/api/mvp/agent/ask-stream")
async def ask_with_ollama_stream(
    request: AgentAskRequest,
    http_request: Request,
) -> StreamingResponse:
    container: AppContainer = http_request.app.state.container
    return StreamingResponse(
        _stream_agent_response(request.message, container),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
