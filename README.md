# AIHost

当前项目是一个可独立运行和测试的 Python AIHost MVP，负责连接 Ollama 与 MCP Server，并对模型选择的工具执行白名单和参数校验。

## 已实现内容

- 使用 FastAPI 应用工厂和显式依赖容器组织启动、路由、Agent、MCP 与 Ollama 边界。
- 每次 Agent 请求重新发现 MCP 工具，并以固定白名单限制模型可见和可调用的工具。
- 支持无需工具的普通回答、模型自动选择工具、多轮工具决策和单轮多个工具调用。
- 普通 JSON 与 SSE 两种 Agent 接口共用同一套工具循环。
- 使用 Draft 2020-12 JSON Schema 校验工具参数，并对未知参数、缺失字段、类型、枚举和范围错误进行分类。
- MCP、Ollama、参数校验和循环上限错误均提供稳定的 `stage`、`code` 与 `retryable` 信息。
- 保留固定时间工具接口作为 MCP 基准链路，并提供独立本地验收页。
- 提供兼容导出，使原有模块导入路径仍可使用。

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
├─ skills/                 # 当前未接入业务的通用基础抽象
├─ integrations/           # Ollama 等外部服务适配器
└─ web/                    # 当前 MVP 的 HTTP 入站路由
```

原有的 `agent_service.py`、`mcp_gateway.py`、`ollama_gateway.py` 和
`config.py` 暂时保留为兼容导出，已有代码可以继续使用原导入路径；新代码应直接依赖上述分层包。

当前 Agent 与 MCP 编排能力包括：

- 最多 5 轮、总计最多 5 次工具调用，限制由统一配置管理。
- 单轮支持多个工具，并将每次结果追加到后续模型上下文。
- 使用 Draft 2020-12 JSON Schema 校验必填项、类型、枚举、范围和未知参数。
- 普通与流式执行共用同一个工具循环，并保留完整 `toolCalls` 追踪结果。
- 内部错误提供稳定的 `stage`、`code` 和 `retryable` 分类。

`AgentContext` 已承载消息历史和用户上下文；`SkillResult` 与 `SkillRegistry` 仅作为通用基础抽象保留，当前没有注册或接入具体业务 Skill。

当前源码包含两条彼此独立的验收路径：

1. 固定基准链路：`tools/list -> 白名单校验 -> tools/call`。
2. Ollama Agent 链路：`tools/list -> 白名单过滤 -> Ollama 决策 -> 可选的多轮 tools/call -> Ollama 最终回答`。

## 本地地址

- AIHost：`http://127.0.0.1:18080`
- 独立验收页：`http://127.0.0.1:18080/mvp`
- MCP Server：`http://127.0.0.1:18081/mcp`
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
2. 启动配置所指向的 MCP Server。
3. 在本目录的 PowerShell 中启动 AIHost：

```powershell
.\.venv\Scripts\python.exe -m app.main
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前没有接入 JWT、数据库、具体业务 Skill、生产 Vue 前端或生产部署配置。独立验收页只用于验证 Python AIHost 已实现的 JSON 与 SSE 链路。
