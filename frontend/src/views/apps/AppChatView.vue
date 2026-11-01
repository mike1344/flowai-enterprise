<template>
  <div class="chat">
    <header class="chat-head">
      <div>
        <h2>{{ slug }}</h2>
        <p class="muted">会话与工单闭环 · 引用与确认均来自服务端</p>
      </div>
      <el-tag v-if="sessionId" size="small" type="success">会话 {{ sessionId }}</el-tag>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <div ref="listEl" class="messages">
      <div v-for="message in messages" :key="message.id" :class="['bubble', message.role === 'USER' ? 'user' : 'assistant']">
        <div class="role">{{ message.role === 'USER' ? '我' : '助手' }}</div>
        <div class="content">{{ message.content }}</div>
        <ul v-if="message.citations?.length" class="citations">
          <li v-for="(c, i) in message.citations" :key="i">
            引用：《{{ c.document_title }}》· {{ c.page_label }}
          </li>
        </ul>
        <div v-if="message.execution_id" class="meta-line">
          <span v-if="executions[message.execution_id]?.llm" class="model-badge">
            模型 {{ executions[message.execution_id].llm.model }}
            · {{ executions[message.execution_id].llm.total_tokens }} tokens
            <template v-if="executions[message.execution_id].llm.status === 'fallback'">（已降级）</template>
          </span>
          <el-button size="small" text type="primary" @click="openSteps(message.execution_id)">执行步骤</el-button>
        </div>
      </div>
    </div>

    <el-card v-if="draft" shadow="never" class="confirm">
      <template #header>工单草稿（需人工确认后才会写入）</template>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="设备">{{ draft.device_id }}</el-descriptions-item>
        <el-descriptions-item label="标题">{{ draft.title }}</el-descriptions-item>
        <el-descriptions-item label="优先级">{{ draft.priority }}</el-descriptions-item>
        <el-descriptions-item label="描述">{{ draft.description }}</el-descriptions-item>
      </el-descriptions>
      <div class="confirm-actions">
        <el-button size="small" @click="reject" :loading="busy">取消</el-button>
        <el-button size="small" type="primary" :loading="busy" @click="confirm">确认创建</el-button>
      </div>
    </el-card>

    <el-card v-if="duplicates.length" shadow="never" class="confirm duplicate">
      <template #header>发现疑似重复工单，是否仍然创建？</template>
      <ul>
        <li v-for="item in duplicates" :key="item.ticket_no">{{ item.ticket_no }} · {{ item.status }}</li>
      </ul>
      <div class="confirm-actions">
        <el-button size="small" @click="reject" :loading="busy">取消</el-button>
        <el-button size="small" type="warning" :loading="busy" @click="confirmDuplicate">仍然创建</el-button>
      </div>
    </el-card>

    <div class="composer">
      <el-input v-model="input" placeholder="例如：device_id: 7 HC200 通信异常，请帮我创建工单" @keyup.enter="send" />
      <el-button type="primary" :loading="busy" @click="send">发送</el-button>
    </div>

    <el-dialog v-model="stepsDialog" title="执行步骤（结构化，不含内部推理）" width="640px">
      <el-descriptions :column="2" size="small" border class="steps-summary">
        <el-descriptions-item label="执行状态">{{ stepsData.status }}</el-descriptions-item>
        <el-descriptions-item label="模型">
          {{ stepsData.llm?.model || '未调用模型' }}
        </el-descriptions-item>
        <el-descriptions-item label="Tokens">
          {{ stepsData.llm?.total_tokens ?? 0 }}
          （prompt {{ stepsData.llm?.prompt_tokens ?? 0 }} / completion {{ stepsData.llm?.completion_tokens ?? 0 }}）
        </el-descriptions-item>
        <el-descriptions-item label="模型延迟">{{ stepsData.llm?.latency_ms ?? '-' }} ms</el-descriptions-item>
      </el-descriptions>
      <el-table :data="stepsData.steps || []" size="small" border>
        <el-table-column prop="step" label="#" width="50" />
        <el-table-column prop="tool_code" label="工具" width="200" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="latency_ms" label="耗时(ms)" width="100" />
        <el-table-column prop="trace_id" label="Trace" />
      </el-table>
      <p v-if="stepsData.error_code" class="muted">错误码：{{ stepsData.error_code }}</p>
    </el-dialog>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'

import { apiGet, apiPost } from '../../api/client'

const props = defineProps({ slug: { type: String, default: 'demo-app' } })

const sessionId = ref(null)
const messages = ref([])
const input = ref('')
const busy = ref(false)
const error = ref('')
const draft = ref(null)
const duplicates = ref([])
const pendingExecution = ref(null)
const executions = ref({})
const stepsDialog = ref(false)
const stepsData = ref({})
const confirmToken = ref('')
const duplicateToken = ref('')
const listEl = ref(null)

function showError(result) {
  error.value = result && result.message ? `${result.code}：${result.message}` : '操作失败'
}

async function ensureSession() {
  if (sessionId.value) return true
  const result = await apiPost('flowai', `/apps/${props.slug}/sessions`, { body: undefined })
  if (!result.ok) {
    showError(result)
    return false
  }
  sessionId.value = result.data.conversation_id
  return true
}

async function loadExecutions(items) {
  const ids = [...new Set(items.filter((m) => Number.isInteger(m.execution_id) && m.execution_id > 0).map((m) => m.execution_id))]
  for (const id of ids) {
    if (executions.value[id]) continue
    const detail = await apiGet('flowai', `/executions/${id}`)
    if (detail.ok) executions.value[id] = detail.data
  }
}

async function openSteps(executionId) {
  const steps = await apiGet('flowai', `/executions/${executionId}/steps`)
  const detail = await apiGet('flowai', `/executions/${executionId}`)
  stepsData.value = { ...(steps.data || {}), llm: (detail.data?.result || {}).llm || null }
  stepsDialog.value = true
}

async function refreshMessages() {
  if (!sessionId.value) return
  const result = await apiGet('flowai', `/sessions/${sessionId.value}/messages`)
  messages.value = result.data.items || []
  await loadExecutions(messages.value)
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

async function send() {
  if (!input.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    if (!(await ensureSession())) return
    const content = input.value
    input.value = ''
    const result = await apiPost('flowai', `/sessions/${sessionId.value}/messages`, { body: { content } })
    if (!result.ok) {
      showError(result)
      return
    }
    const data = result.data
    pendingExecution.value = data.execution_id
    if (data.status === 'WAITING_CONFIRMATION') {
      draft.value = data.draft
      confirmToken.value = data.confirmation_token
    } else if (data.status === 'WAITING_DUPLICATE_CONFIRMATION') {
      duplicates.value = []
    }
    await refreshMessages()
  } finally {
    busy.value = false
  }
}

async function confirm() {
  if (!pendingExecution.value) return
  busy.value = true
  try {
    const result = await apiPost('flowai', `/executions/${pendingExecution.value}/confirm`, {
      body: { token: confirmToken.value }
    })
    if (!result.ok) {
      showError(result)
      return
    }
    const data = result.data
    if (data.status === 'WAITING_DUPLICATE_CONFIRMATION') {
      draft.value = null
      duplicates.value = data.existing_tickets || []
      duplicateToken.value = data.duplicate_confirmation_token || ''
    } else {
      draft.value = null
      duplicates.value = []
      pendingExecution.value = null
    }
    await refreshMessages()
  } finally {
    busy.value = false
  }
}

async function confirmDuplicate() {
  if (!pendingExecution.value) return
  busy.value = true
  try {
    const result = await apiPost('flowai', `/executions/${pendingExecution.value}/confirm-duplicate`, {
      body: { token: duplicateToken.value }
    })
    if (!result.ok) {
      showError(result)
      return
    }
    duplicates.value = []
    pendingExecution.value = null
    await refreshMessages()
  } finally {
    busy.value = false
  }
}

async function reject() {
  if (!pendingExecution.value) return
  busy.value = true
  try {
    await apiPost('flowai', `/executions/${pendingExecution.value}/reject`)
    draft.value = null
    duplicates.value = []
    pendingExecution.value = null
    await refreshMessages()
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await ensureSession()
  await refreshMessages()
})
</script>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat-head h2 {
  margin: 0;
  font-size: 18px;
  color: #17324d;
}
.muted {
  margin: 4px 0 0;
  font-size: 12px;
  color: #7c8fa3;
}
.messages {
  max-height: 420px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px;
}
.bubble {
  max-width: 78%;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.6;
}
.bubble.user {
  align-self: flex-end;
  background: #e8f1fb;
  color: #17324d;
}
.bubble.assistant {
  align-self: flex-start;
  background: #fff;
  border: 1px solid #e6ecf3;
}
.role {
  font-size: 11px;
  color: #7c8fa3;
  margin-bottom: 4px;
}
.content {
  white-space: pre-wrap;
}
.citations {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 12px;
  color: #2b6cb0;
}
.confirm-actions {
  margin-top: 12px;
  text-align: right;
}
.duplicate {
  border-color: #f0c36b;
}
.composer {
  display: flex;
  gap: 8px;
}
</style>