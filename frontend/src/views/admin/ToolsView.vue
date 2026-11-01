<template>
  <div>
    <div class="head">
      <h2>工具中心</h2>
      <div class="hint">只允许预置白名单工具；工具参数在服务端按 JSON Schema 校验</div>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <el-row :gutter="16">
      <el-col :md="10">
        <el-card shadow="never">
          <template #header>预置工具（{{ tools.length }}）</template>
          <el-table :data="tools" size="small" border>
            <el-table-column prop="name" label="名称" width="130" />
            <el-table-column prop="tool_code" label="code" width="170" />
            <el-table-column label="类型" width="80">
              <template #default="{ row }">
                <el-tag :type="row.kind === 'WRITE' ? 'warning' : 'success'" size="small">{{ row.kind }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :md="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>应用工具授权</span>
              <el-select v-model="appId" size="small" placeholder="选择应用" style="width: 220px" @change="loadBound">
                <el-option v-for="app in apps" :key="app.id" :label="`${app.name}（${app.slug}）`" :value="app.id" />
              </el-select>
            </div>
          </template>
          <el-table :data="tools" size="small" border>
            <el-table-column prop="name" label="工具" width="140" />
            <el-table-column label="参数 Schema" min-width="260">
              <template #default="{ row }">
                <code class="schema">{{ requiredFields(row) }}</code>
              </template>
            </el-table-column>
            <el-table-column label="授权" width="110">
              <template #default="{ row }">
                <el-switch
                  :model-value="boundCodes.includes(row.tool_code)"
                  :disabled="!appId || saving"
                  @change="(value) => toggle(row.tool_code, value)"
                />
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!appId" class="muted">先选择应用查看/调整授权</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { apiDelete, apiGet, apiPost } from '../../api/client'

const tools = ref([])
const apps = ref([])
const appId = ref(null)
const boundCodes = ref([])
const saving = ref(false)
const error = ref('')

function requiredFields(tool) {
  const schema = tool.input_schema || {}
  const required = schema.required || []
  const props = Object.keys(schema.properties || {})
  return `参数：${props.join(', ') || '无'}${required.length ? '；必填：' + required.join(', ') : ''}`
}

async function load() {
  const [toolResp, appResp] = await Promise.all([
    apiGet('flowai', '/tools'),
    apiGet('flowai', '/applications')
  ])
  if (!toolResp.ok) error.value = `${toolResp.code}：${toolResp.message}`
  tools.value = toolResp.data.items || []
  apps.value = appResp.data.items || []
  if (!appId.value && apps.value.length) {
    appId.value = apps.value[0].id
    await loadBound()
  }
}

async function loadBound() {
  if (!appId.value) return
  const result = await apiGet('flowai', `/applications/${appId.value}/tools`)
  boundCodes.value = (result.data.items || []).map((item) => item.tool_code)
}

async function toggle(code, enabled) {
  saving.value = true
  try {
    if (enabled) {
      await apiPost('flowai', `/applications/${appId.value}/tools/${code}`)
    } else {
      await apiDelete('flowai', `/applications/${appId.value}/tools/${code}`)
    }
    await loadBound()
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.head {
  margin-bottom: 12px;
}
.head h2 {
  margin: 0 0 4px;
  font-size: 18px;
  color: #17324d;
}
.hint {
  font-size: 12px;
  color: #7c8fa3;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.schema {
  font-size: 12px;
  color: #4a5c6e;
}
.muted {
  margin-top: 8px;
  font-size: 12px;
  color: #9aa9b8;
}
</style>