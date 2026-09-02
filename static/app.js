const agentForm = document.querySelector('#agent-form')
const messageInput = document.querySelector('#message')
const askButton = document.querySelector('#ask-button')
const rawOutput = document.querySelector('#raw-output')
const summary = document.querySelector('#summary')
const mode = document.querySelector('#mode')
const model = document.querySelector('#model')
const toolName = document.querySelector('#tool-name')
const answer = document.querySelector('#answer')
const elapsed = document.querySelector('#elapsed')
const httpStatus = document.querySelector('#http-status')
const listStatus = document.querySelector('#list-status')
const decisionStatus = document.querySelector('#decision-status')
const callStatus = document.querySelector('#call-status')
const answerStatus = document.querySelector('#answer-status')
const baselineButton = document.querySelector('#baseline-button')
const baselineOutput = document.querySelector('#baseline-output')

function setStatus(element, text, state = '') {
  element.textContent = text
  element.className = `status ${state ? `status-${state}` : ''}`.trim()
}

function resetAgentCall() {
  setStatus(listStatus, '等待中', 'pending')
  setStatus(decisionStatus, '等待中', 'pending')
  setStatus(callStatus, '等待中', 'pending')
  setStatus(answerStatus, '等待中', 'pending')
  summary.textContent = '正在等待 SSE 事件…'
  mode.textContent = '—'
  model.textContent = '—'
  toolName.textContent = '—'
  answer.textContent = ''
  elapsed.textContent = '—'
  httpStatus.textContent = '连接中'
  rawOutput.textContent = ''
}

function appendRawEvent(line) {
  rawOutput.textContent += `${line}\n`
  rawOutput.scrollTop = rawOutput.scrollHeight
}

function showStreamError(event) {
  const stageTargets = {
    tools_list: listStatus,
    tool_validation: callStatus,
    tool_call: callStatus,
    ollama_connect: decisionStatus,
    ollama_decision: decisionStatus,
    ollama_final: answerStatus,
    unexpected: answerStatus,
  }
  setStatus(stageTargets[event.stage] || answerStatus, '失败', 'error')
  summary.textContent = event.content || 'SSE 调用失败'
}

function handleStreamEvent(event, state) {
  switch (event.type) {
    case 'meta':
      model.textContent = event.model || '—'
      break

    case 'status':
      summary.textContent = event.content || '处理中…'
      if (event.stage === 'tools_list') {
        setStatus(listStatus, '执行中', 'pending')
      } else if (event.stage === 'ollama_decision') {
        setStatus(listStatus, '成功', 'ok')
        setStatus(decisionStatus, '决策中', 'pending')
      } else if (event.stage === 'tool_call') {
        setStatus(decisionStatus, '选择工具', 'ok')
        setStatus(callStatus, '调用中', 'pending')
      } else if (event.stage === 'ollama_final') {
        if (state.mode === 'general') setStatus(callStatus, '未调用')
        setStatus(answerStatus, '生成中', 'pending')
      }
      break

    case 'classify':
      state.mode = event.mode || ''
      mode.textContent = event.mode === 'tool' ? '工具调用' : '普通回答'
      setStatus(decisionStatus, event.mode === 'tool' ? '选择工具' : '普通回答', 'ok')
      break

    case 'tool_result':
      toolName.textContent = event.toolName || '—'
      setStatus(callStatus, '调用成功', 'ok')
      break

    case 'response':
      if (event.content) {
        state.content += event.content
        answer.textContent = state.content
        setStatus(answerStatus, '接收中', 'pending')
      }
      break

    case 'error':
      state.failed = true
      showStreamError(event)
      break
  }
}

function finishStream(state, startedAt) {
  elapsed.textContent = `${Math.round(performance.now() - startedAt)} ms`
  if (state.failed) return

  if (!state.content) answer.textContent = '—'
  setStatus(answerStatus, '成功', 'ok')
  summary.textContent = state.mode === 'tool'
    ? '工具调用完成，SSE 流式回答接收完毕。'
    : '模型判断无需调用工具，SSE 流式回答接收完毕。'
}

document.querySelectorAll('.example-button').forEach((button) => {
  button.addEventListener('click', () => {
    messageInput.value = button.dataset.prompt || ''
    messageInput.focus()
  })
})

agentForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  const message = messageInput.value.trim()
  if (!message) {
    messageInput.focus()
    return
  }

  askButton.disabled = true
  resetAgentCall()
  const startedAt = performance.now()
  const state = { mode: '', content: '', failed: false, done: false }

  try {
    const response = await fetch('/api/mvp/agent/ask-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    httpStatus.textContent = `HTTP ${response.status}`

    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const reader = response.body?.getReader()
    if (!reader) throw new Error('无法读取 SSE 响应流')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue

        const data = trimmed.substring(6)
        appendRawEvent(trimmed)

        if (data === '[DONE]') {
          state.done = true
          finishStream(state, startedAt)
          continue
        }

        try {
          handleStreamEvent(JSON.parse(data), state)
        } catch {
          state.failed = true
          showStreamError({ stage: 'unexpected', content: '收到无法解析的 SSE 事件' })
        }
      }
    }

    if (!state.done && !state.failed) {
      state.failed = true
      showStreamError({ stage: 'unexpected', content: 'SSE 连接结束但未收到 [DONE]' })
    }
  } catch (error) {
    state.failed = true
    setStatus(answerStatus, '失败', 'error')
    summary.textContent = `无法完成 SSE 请求：${String(error)}`
    httpStatus.textContent = httpStatus.textContent === '连接中' ? '网络错误' : httpStatus.textContent
  } finally {
    askButton.disabled = false
  }
})

baselineButton.addEventListener('click', async () => {
  baselineButton.disabled = true
  baselineOutput.textContent = '正在执行固定 MCP 基准链路…'

  try {
    const response = await fetch('/api/mvp/tools/get_current_date_time/call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    const payload = await response.json()
    baselineOutput.textContent = JSON.stringify(payload, null, 2)
  } catch (error) {
    baselineOutput.textContent = String(error)
  } finally {
    baselineButton.disabled = false
  }
})
