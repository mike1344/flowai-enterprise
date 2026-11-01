<template>
  <div>
    <div class="head">
      <h2>模型配置</h2>
      <div class="hint">密钥只保存环境变量名（API Key Ref），服务端从不回显密钥</div>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <el-card shadow="never" class="panel">
      <template #header>新建模型配置</template>
      <el-form :model="form" label-width="120px" size="small" class="form">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="deepseek-chat" style="width: 240px" />
        </el-form-item>
        <el-form-item label="协议">
          <el-select v-model="form.provider" style="width: 240px">
            <el-option label="OPENAI_COMPATIBLE" value="OPENAI_COMPATIBLE" />
            <el-option label="LOCAL_HTTP" value="LOCAL_HTTP" />
            <el-option label="MOCK" value="MOCK" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="form.base_url" placeholder="https://api.deepseek.com/v1" style="width: 360px" />
        </el-form-item>
        <el-form-item label="模型名">
          <el-input v-model="form.model_name" placeholder="deepseek-chat" style="width: 240px" />
        </el-form-item>
        <el-form-item label="密钥环境变量名">
          <el-input v-model="form.api_key_ref" placeholder="FLOWAI_LLM_API_KEY" style="width: 240px" />
          <span class="muted">例：FLOWAI_LLM_API_KEY（真实密钥写在 .env，不入库、不回显）</span>
        </el-form-item>
        <el-form-item label="温度 / 上限">
          <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" />
          <el-input-number v-model="form.max_tokens" :min="16" :max="8192" :step="64" style="margin-left: 8px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="createModel">创建</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="panel">
      <template #header>已配置模型（{{ models.length }}）</template>
      <el-table :data="models" size="small" border>
        <el-table-column prop="name" label="名称" width="160" />
        <el-table-column prop="provider" label="协议" width="170" />
        <el-table-column prop="base_url" label="Base URL" min-width="240" />
        <el-table-column prop="model_name" label="模型名" width="160" />
        <el-table-column label="密钥" width="150">
          <template #default="{ row }">
            <el-tag :type="row.api_key_configured ? 'success' : 'danger'" size="small">
              {{ row.api_key_configured ? '已配置' : '未配置' }}
            </el-tag>
            <div class="muted small">{{ row.api_key_ref || '—' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" :loading="testing === row.id" @click="testOne(row)">连通性测试</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="lastTest" class="test-result">
        <el-alert
          :type="lastTest.ok ? 'success' : 'error'"
          :title="`${lastTest.name}：${lastTest.ok ? '连接成功' : '连接失败'}`"
          :description="lastTest.detail"
          :closable="false"
          show-icon
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { apiGet, apiPost } from '../../api/client'

const models = ref([])
const saving = ref(false)
const testing = ref(null)
const error = ref('')
const lastTest = ref(null)

const form = reactive({
  name: 'deepseek-chat',
  provider: 'OPENAI_COMPATIBLE',
  base_url: 'https://api.deepseek.com/v1',
  model_name: 'deepseek-chat',
  api_key_ref: 'FLOWAI_LLM_API_KEY',
  temperature: 0.3,
  max_tokens: 512
})

async function load() {
  const result = await apiGet('flowai', '/models')
  if (!result.ok) {
    error.value = result.code + '：' + result.message
    return
  }
  models.value = result.data.items || []
}

async function createModel() {
  saving.value = true
  error.value = ''
  try {
    const result = await apiPost('flowai', '/models', { body: { ...form } })
    if (!result.ok) {
      error.value = result.code + '：' + result.message
      return
    }
    await load()
  } finally {
    saving.value = false
  }
}

async function testOne(row) {
  testing.value = row.id
  lastTest.value = null
  try {
    const result = await apiPost('flowai', `/models/${row.id}/test`)
    lastTest.value = {
      name: row.name,
      ok: Boolean(result.ok && result.data?.ok),
      detail: result.ok ? (result.data?.message || '') : result.code + '：' + result.message
    }
  } finally {
    testing.value = null
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
.panel {
  margin-bottom: 12px;
}
.form {
  max-width: 760px;
}
.muted {
  font-size: 12px;
  color: #9aa9b8;
  margin-left: 8px;
}
.small {
  margin-top: 2px;
}
.test-result {
  margin-top: 10px;
}
</style>