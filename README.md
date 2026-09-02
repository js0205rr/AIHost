# AIHost

本项目用于分阶段验证 CUBIC AIHost 的 Python 迁移链路。

## 当前框架结构

项目采用模块化单体结构，外部入口、应用编排和外部服务适配相互分离：

```text
app/
├─ main.py                 # 进程启动入口
├─ bootstrap.py            # FastAPI 应用工厂
├─ container.py            # 显式依赖装配
├─ core/                   # 统一配置和跨模块错误类型
├─ agent/                  # Agent 上下文、依赖端口和应用编排
├─ mcp/                    # MCP 工具发现、白名单和调用边界
├─ skills/                 # Skill 定义、统一结果和命令注册表
├─ integrations/           # Ollama 等外部服务适配器
└─ web/                    # 当前 MVP 的 HTTP 入站路由
```

原有的 `agent_service.py`、`mcp_gateway.py`、`ollama_gateway.py` 和
`config.py` 暂时保留为兼容导出，已有代码可以继续使用原导入路径；新代码应直接依赖上述分层包。

阶段 2 已建立与传输协议无关的 `AgentContext`、`SkillResult` 和 `SkillRegistry`。
具体业务 Skill、数据库、鉴权及对外 API 契约将在后续阶段逐项迁移。

当前源码包含两条彼此独立的验收路径：

1. 固定基准链路：`tools/list -> 白名单校验 -> tools/call`。
2. Ollama Agent 链路：`tools/list -> 白名单过滤 -> Ollama 决策 -> 可选 tools/call -> Ollama SSE 流式回答`。

## 本地地址

- AIHost：`http://127.0.0.1:18080`
- 独立验收页：`http://127.0.0.1:18080/mvp`
- Python MCP Server：`http://127.0.0.1:18081/mcp`
- Ollama：`http://127.0.0.1:11434`
- 当前模型：`qwen3:0.6b`

## API

固定基准接口：

```text
POST /api/mvp/tools/get_current_date_time/call
{}
```

Ollama Agent 接口：

```text
POST /api/mvp/agent/ask
{"message":"现在几点了？"}
```

Ollama Agent SSE 接口：

```text
POST /api/mvp/agent/ask-stream
Content-Type: application/json
Accept: text/event-stream
{"message":"现在几点了？"}
```

SSE 事件沿用旧 C# AIHost 与 Vue 前端使用的协议：`meta`、`status`、`classify`、`tool_result`、`response`、`error`，并以 `data: [DONE]` 结束。工具决策保持非流式，最终自然语言回答使用 Ollama 真流式输出。

Agent 接口每次请求都会重新执行 `tools/list`，只把 AIHost 固定白名单中的工具提供给模型。模型返回工具调用后，AIHost 会再次校验工具名和参数，再执行 `tools/call`。

## 启动顺序

1. 确认 WSL 中的 Ollama 服务和 `qwen3:0.6b` 已可用。
2. 启动同级项目 `CUBIC-McpServer-Python`。
3. 在本目录的 PowerShell 中启动 AIHost：

```powershell
.\.venv\Scripts\python.exe -m app.main
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前仍不包含 JWT、Vue 接入、数据库、RAG 和生产部署配置。独立验收页使用 Python AIHost 提供的 SSE 接口，不接入现有 Vue 仓库。
