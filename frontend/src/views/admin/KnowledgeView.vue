<template>
  <div>
    <div class="head">
      <h2>知识库</h2>
      <div class="actions">
        <el-input v-model="name" placeholder="知识库名称" size="small" style="width: 160px" />
        <el-button type="primary" size="small" @click="createKb">新建知识库</el-button>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <el-row :gutter="16">
      <el-col :md="10">
        <el-table :data="kbs" size="small" border highlight-current-row @current-change="selectKb">
          <el-table-column prop="name" label="名称" />
          <el-table-column label="文档" width="90">
            <template #default="{ row }">{{ row.stats.documents }}</template>
          </el-table-column>
          <el-table-column label="分块" width="90">
            <template #default="{ row }">{{ row.stats.chunks }}</template>
          </el-table-column>
        </el-table>
      </el-col>
      <el-col :md="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span>{{ current ? current.name : '选择左侧知识库' }}</span>
              <span v-if="current" class="muted">已就绪 {{ current.stats.ready_documents }} / {{ current.stats.documents }}</span>
            </div>
          </template>

          <div v-if="current">
            <div class="upload">
              <input ref="fileInput" type="file" accept=".pdf,.docx,.txt,.md" @change="onFile" />
              <el-button size="small" type="primary" :loading="uploading" @click="upload">上传并解析</el-button>
            </div>

            <el-table :data="documents" size="small" border class="mt">
              <el-table-column prop="title" label="文档" />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'READY' ? 'success' : row.status === 'FAILED' ? 'danger' : 'warning'" size="small">
                    {{ row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="error_message" label="错误" />
            </el-table>

            <div class="index-bar">
              <el-button size="small" @click="loadIndexes">索引版本</el-button>
              <span v-if="activeVersionNo" class="muted">当前 active：v{{ activeVersionNo }}</span>
            </div>

            <div class="search">
              <el-input v-model="query" placeholder="检索测试（需先给用户授予该 KB 的 READ 权限）" size="small" />
              <el-button size="small" @click="search">检索</el-button>
            </div>
            <el-alert
              v-if="searchResult"
              :type="searchResult.refused ? 'warning' : 'success'"
              :title="searchResult.refused ? `拒答：${searchResult.reason}` : `命中 ${searchResult.items.length} 条证据`"
              :description="searchResult.answer"
              :closable="false"
              show-icon
            />
            <ul v-if="searchResult?.citations?.length" class="citations">
              <li v-for="(c, i) in searchResult.citations" :key="i">
                《{{ c.document_title }}》· {{ c.page_label }} · chunk {{ c.chunk_id }}
              </li>
            </ul>
          </div>
          <el-empty v-else description="尚未选择知识库" />
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="indexDialog" :title="`索引版本 · ${current?.name || ''}`" width="660px">
      <el-table :data="indexes" size="small" border>
        <el-table-column prop="version_no" label="版本" width="70" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="chunk_count" label="分块" width="80" />
        <el-table-column label="当前" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="success" size="small">active</el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              size="small"
              :disabled="row.is_active || row.status === 'FAILED' || row.status === 'BUILDING'"
              @click="activateIndex(row)"
            >切回</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="muted">只有 READY / DEPRECATED 可切回；构建失败不会覆盖旧索引。</p>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { apiGet, apiPost, uploadFile } from '../../api/client'

const kbs = ref([])
const current = ref(null)
const documents = ref([])
const name = ref('')
const error = ref('')
const query = ref('')
const searchResult = ref(null)
const uploading = ref(false)
const fileInput = ref(null)
const indexDialog = ref(false)
const indexes = ref([])
const activeVersionNo = ref(null)
let pendingFile = null

async function load() {
  const result = await apiGet('flowai', '/knowledge-bases')
  if (!result.ok) {
    error.value = `${result.code}：${result.message}`
    return
  }
  kbs.value = result.data.items || []
  if (!current.value && kbs.value.length) selectKb(kbs.value[0])
}

async function createKb() {
  const result = await apiPost('flowai', '/knowledge-bases', { body: { name: name.value } })
  if (!result.ok) error.value = `${result.code}：${result.message}`
  name.value = ''
  await load()
}

async function selectKb(row) {
  if (!row) return
  current.value = row
  const docs = await apiGet('flowai', `/knowledge-bases/${row.id}/documents`)
  documents.value = docs.data.items || []
}

function onFile(event) {
  pendingFile = event.target.files?.[0] || null
}

async function upload() {
  if (!pendingFile || !current.value) return
  uploading.value = true
  error.value = ''
  try {
    const result = await uploadFile('flowai', `/knowledge-bases/${current.value.id}/documents/upload`, pendingFile)
    if (result.data.status === 'FAILED') error.value = `解析失败：${result.data.error_message}`
    pendingFile = null
    if (fileInput.value) fileInput.value.value = ''
    await load()
  } finally {
    uploading.value = false
  }
}

async function loadIndexes() {
  if (!current.value) return
  const result = await apiGet('flowai', `/knowledge-bases/${current.value.id}/indexes`)
  indexes.value = result.data.items || []
  const active = indexes.value.find((item) => item.is_active)
  activeVersionNo.value = active ? active.version_no : null
  indexDialog.value = true
}

async function activateIndex(row) {
  if (!current.value) return
  const result = await apiPost('flowai', `/knowledge-bases/${current.value.id}/indexes/${row.id}/activate`)
  if (!result.ok) error.value = result.code + '：' + result.message
  await loadIndexes()
}

async function search() {
  if (!current.value) return
  // 检索属于应用维度：取第一个已绑定该 KB 的应用
  const apps = await apiGet('flowai', '/applications')
  let target = null
  for (const app of apps.data.items || []) {
    const bound = await apiGet('flowai', `/applications/${app.id}/knowledge-bases`)
    if ((bound.data.items || []).some((kb) => kb.id === current.value.id)) {
      target = app
      break
    }
  }
  if (!target) {
    searchResult.value = { refused: true, reason: 'APP_HAS_NO_KB', answer: '没有应用绑定该知识库', citations: [] }
    return
  }
  const result = await apiPost('flowai', '/knowledge-bases/search-test', {
    body: { application_id: target.id, query: query.value }
  })
  searchResult.value = result.data
}

onMounted(load)
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.head h2 {
  margin: 0;
  font-size: 18px;
  color: #17324d;
}
.card-head {
  display: flex;
  justify-content: space-between;
}
.muted {
  color: #9aa9b8;
  font-size: 12px;
}
.upload {
  display: flex;
  gap: 12px;
  align-items: center;
}
.mt {
  margin-top: 12px;
}
.search {
  display: flex;
  gap: 8px;
  margin: 16px 0 8px;
}
.citations {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: #2b6cb0;
}
</style>