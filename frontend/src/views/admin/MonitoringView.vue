<template>
  <div>
    <div class="head">
      <h2>监控与审计</h2>
      <div class="actions">
        <el-input v-model="traceId" placeholder="按 Trace ID 查询" size="small" style="width: 260px" />
        <el-button size="small" @click="lookupTrace">查询</el-button>
        <el-button size="small" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <el-row :gutter="16" class="cards">
      <el-col :xs="12" :md="6">
        <el-card shadow="never"><div class="label">请求量</div><div class="value">{{ metrics.requests ?? '-' }}</div></el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never"><div class="label">错误率</div><div class="value">{{ ((metrics.error_rate ?? 0) * 100).toFixed(2) }}%</div></el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never"><div class="label">P95</div><div class="value">{{ metrics.latency_ms?.p95 ?? '-' }} ms</div></el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never">
          <div class="label">Token（真实模型）</div>
          <div class="value">{{ metrics.token_usage?.total ?? 0 }}</div>
          <div class="small">调用 {{ metrics.token_usage?.llm_calls ?? 0 }} 次</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="trace" shadow="never" class="panel">
      <template #header>Trace 详情 · {{ trace.trace_id }}（{{ trace.found ? '已找到' : '未找到' }}）</template>
      <el-row :gutter="12">
        <el-col :md="8">
          <h4>审计</h4>
          <ul class="list">
            <li v-for="(item, i) in trace.audit" :key="i">{{ item.action }} · {{ item.outcome }} · {{ item.actor_ref }}</li>
          </ul>
        </el-col>
        <el-col :md="8">
          <h4>工具调用</h4>
          <ul class="list">
            <li v-for="(item, i) in trace.tool_calls" :key="i">{{ item.tool_code }} · {{ item.status }} · {{ item.latency_ms }}ms</li>
          </ul>
        </el-col>
        <el-col :md="8">
          <h4>执行 / 请求</h4>
          <ul class="list">
            <li v-for="(item, i) in trace.executions" :key="i">执行 #{{ item.id }} · {{ item.status }}</li>
            <li v-for="(item, i) in trace.requests" :key="'r' + i">{{ item.method }} {{ item.path }} · {{ item.status }} · {{ item.latency_ms }}ms</li>
          </ul>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="panel">
      <template #header>审计日志（最近 50 条）</template>
      <el-table :data="audit" size="small" border>
        <el-table-column prop="created_at" label="时间" width="200" />
        <el-table-column prop="action" label="动作" width="180" />
        <el-table-column prop="actor_ref" label="操作者" width="120" />
        <el-table-column prop="outcome" label="结果" width="90" />
        <el-table-column prop="trace_id" label="Trace" min-width="220" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'

const metrics = ref({})
const audit = ref([])
const trace = ref(null)
const traceId = ref('')
const error = ref('')

async function loadAll() {
  error.value = ''
  const [metricsResp, auditResp] = await Promise.all([
    apiGet('flowai', '/monitoring/metrics?window_minutes=60'),
    apiGet('flowai', '/monitoring/audit?limit=50')
  ])
  if (!metricsResp.ok) error.value = `${metricsResp.code}：${metricsResp.message}`
  metrics.value = metricsResp.data
  audit.value = auditResp.data.items || []
}

async function lookupTrace() {
  if (!traceId.value.trim()) return
  const result = await apiGet('flowai', `/monitoring/traces/${traceId.value.trim()}`)
  if (!result.ok) {
    error.value = `${result.code}：${result.message}`
    return
  }
  error.value = ''
  trace.value = result.data
}

onMounted(loadAll)
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.head h2 {
  margin: 0;
  font-size: 18px;
  color: #17324d;
}
.actions {
  display: flex;
  gap: 8px;
}
.cards {
  margin-bottom: 12px;
}
.label {
  font-size: 12px;
  color: #7c8fa3;
}
.value {
  font-size: 22px;
  font-weight: 700;
  color: #17324d;
  margin-top: 4px;
}
.small {
  font-size: 11px;
  color: #9aa9b8;
}
.panel {
  margin-bottom: 12px;
}
.list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #4a5c6e;
  line-height: 1.8;
}
</style>