<template>
  <div>
    <div class="head">
      <h2>AI 应用</h2>
      <div class="actions">
        <el-select v-model="modelId" placeholder="选择模型" size="small" style="width: 160px">
          <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
        <el-input v-model="form.name" placeholder="应用名称" size="small" style="width: 140px" />
        <el-input v-model="form.slug" placeholder="slug" size="small" style="width: 120px" />
        <el-button type="primary" size="small" :loading="saving" @click="create">新建应用</el-button>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-table :data="apps" size="small" border v-loading="loading">
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="slug" label="slug" width="140" />
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'PUBLISHED' ? 'success' : row.status === 'DISABLED' ? 'info' : 'warning'" size="small">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="已绑定工具" width="200">
        <template #default="{ row }">
          <span v-if="toolMap[row.id]?.length">{{ toolMap[row.id].join(', ') }}</span>
          <span v-else class="muted">未绑定</span>
        </template>
      </el-table-column>
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button size="small" @click="publish(row)" :disabled="row.status === 'PUBLISHED'">发布</el-button>
          <el-button size="small" @click="openTest(row)">草稿测试</el-button>
          <el-button size="small" @click="openTools(row)">工具授权</el-button>
          <el-button size="small" @click="openVersions(row)">版本</el-button>
          <el-button size="small" @click="$router.push(`/apps/${row.slug}`)">打开</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="testDialog" :title="`草稿测试 · ${currentApp?.name || ''}`" width="640px">
      <p class="muted">对当前草稿配置发起一次真实模型调用，用于发布前验证（不影响已发布版本）。</p>
      <el-input v-model="testPrompt" type="textarea" :rows="3" placeholder="输入测试问题，例如：介绍一下你能做什么" />
      <div class="dialog-actions">
        <el-button type="primary" size="small" :loading="testing" @click="runTest">运行测试</el-button>
      </div>
      <el-alert
        v-if="testResult"
        class="test-alert"
        :type="testResult.ok ? 'success' : 'error'"
        :title="testResult.ok ? '测试成功' : '测试失败'"
        :description="testResult.detail"
        :closable="false"
        show-icon
      />
    </el-dialog>

    <el-dialog v-model="versionDialog" :title="`版本历史 · ${currentApp?.name || ''}`" width="720px">
      <el-table :data="versions" size="small" border>
        <el-table-column prop="version_no" label="版本" width="70" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'PUBLISHED' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="published_at" label="发布时间" width="200" />
        <el-table-column label="系统提示词" min-width="260">
          <template #default="{ row }">{{ (row.config?.system_prompt || '').slice(0, 60) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button size="small" :disabled="row.status === 'PUBLISHED'" @click="rollback(row)">回滚到此版本</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="muted">快照内容不可变；回滚只切换当前发布版本，权限仍按当前策略校验。</p>
    </el-dialog>

    <el-dialog v-model="toolDialog" title="工具授权" width="520px">
      <div v-if="currentApp">
        <p class="muted">{{ currentApp.name }} · 只允许白名单工具</p>
        <el-checkbox-group v-model="selectedTools">
          <el-checkbox v-for="tool in tools" :key="tool.tool_code" :value="tool.tool_code" :label="tool.tool_code">
            {{ tool.name }} ({{ tool.kind }})
          </el-checkbox>
        </el-checkbox-group>
        <div class="dialog-actions">
          <el-button type="primary" :loading="saving" @click="saveTools">保存授权</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { apiDelete, apiGet, apiPost } from '../../api/client'

const apps = ref([])
const models = ref([])
const tools = ref([])
const toolMap = ref({})
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const modelId = ref(null)
const form = reactive({ name: '', slug: '' })
const toolDialog = ref(false)
const currentApp = ref(null)
const selectedTools = ref([])

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [appResp, modelResp, toolResp] = await Promise.all([
      apiGet('flowai', '/applications'),
      apiGet('flowai', '/models'),
      apiGet('flowai', '/tools')
    ])
    if (!appResp.ok) error.value = appResp.message || appResp.code
    apps.value = appResp.data.items || []
    models.value = modelResp.data.items || []
    tools.value = toolResp.data.items || []
    if (!modelId.value && models.value.length) modelId.value = models.value[0].id

    const map = {}
    for (const app of apps.value) {
      const bound = await apiGet('flowai', `/applications/${app.id}/tools`)
      map[app.id] = (bound.data.items || []).map((item) => item.tool_code)
    }
    toolMap.value = map
  } finally {
    loading.value = false
  }
}

async function create() {
  saving.value = true
  error.value = ''
  try {
    const result = await apiPost('flowai', '/applications', {
      body: {
        name: form.name,
        slug: form.slug,
        config: { model_config_id: modelId.value, system_prompt: `你是 ${form.name} 助手` }
      }
    })
    if (!result.ok) {
      error.value = `${result.code}：${result.message}`
      return
    }
    form.name = ''
    form.slug = ''
    await load()
  } finally {
    saving.value = false
  }
}

async function publish(row) {
  const result = await apiPost('flowai', `/applications/${row.id}/publish`)
  if (!result.ok) error.value = `${result.code}：${result.message}`
  await load()
}

async function openTools(row) {
  currentApp.value = row
  selectedTools.value = [...(toolMap.value[row.id] || [])]
  toolDialog.value = true
}

async function saveTools() {
  saving.value = true
  try {
    const existing = toolMap.value[currentApp.value.id] || []
    for (const code of selectedTools.value.filter((code) => !existing.includes(code))) {
      await apiPost('flowai', `/applications/${currentApp.value.id}/tools/${code}`)
    }
    for (const code of existing.filter((code) => !selectedTools.value.includes(code))) {
      await apiDelete('flowai', `/applications/${currentApp.value.id}/tools/${code}`)
    }
    toolDialog.value = false
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.head h2 {
  margin: 0;
  font-size: 18px;
  color: #17324d;
}
.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.muted {
  color: #9aa9b8;
  font-size: 12px;
}
.dialog-actions {
  margin-top: 16px;
  text-align: right;
}
</style>