<template>
  <div class="entry">
    <el-card shadow="never">
      <template #header>应用入口 · {{ slug }}</template>

      <p class="lead">
        该地址即已发布应用的独立入口（<code>/apps/{{ slug }}</code>）。应用发布快照与访问授权将在
        M02-03 / M02-01 完成后接入；当前仅验证前端到后端链路的真实连通性。
      </p>

      <el-descriptions :column="1" size="small" border class="desc">
        <el-descriptions-item label="调用地址">/api/flowai/meta</el-descriptions-item>
        <el-descriptions-item label="结果">
          <el-tag :type="result && result.ok ? 'success' : 'danger'" size="small">
            {{ result ? (result.ok ? '连通' : '失败') : '调用中' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="服务">{{ result?.data?.service || '-' }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ result?.data?.version || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Trace ID">
          <code>{{ result?.traceId || '-' }}</code>
        </el-descriptions-item>
        <el-descriptions-item v-if="result && !result.ok" label="错误">
          {{ result.code }} {{ result.message }}
        </el-descriptions-item>
      </el-descriptions>

      <el-button class="retry" :loading="loading" @click="load">重新检测</el-button>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'

const props = defineProps({
  slug: { type: String, default: 'demo-app' }
})

const loading = ref(false)
const result = ref(null)

async function load() {
  loading.value = true
  try {
    result.value = await apiGet('flowai', '/meta')
  } finally {
    loading.value = false
  }
}

onMounted(load)

defineExpose({ slug: props.slug })
</script>

<style scoped>
.entry {
  max-width: 760px;
}
.lead {
  font-size: 13px;
  color: #4a5c6e;
  line-height: 1.7;
}
.desc {
  margin: 12px 0 16px;
}
code {
  font-size: 12px;
  color: #2b6cb0;
}
</style>