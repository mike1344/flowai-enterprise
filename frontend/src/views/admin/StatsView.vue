<template>
  <div>
    <div class="head">
      <h2>运行统计</h2>
      <div class="actions">
        <el-select v-model="windowMinutes" size="small" style="width: 120px" @change="load">
          <el-option :value="15" label="最近 15 分钟" />
          <el-option :value="60" label="最近 60 分钟" />
          <el-option :value="1440" label="最近 24 小时" />
        </el-select>
        <el-button size="small" @click="load">刷新</el-button>
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
        <el-card shadow="never"><div class="label">P95 延迟</div><div class="value">{{ metrics.latency_ms?.p95 ?? '-' }} ms</div></el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="never"><div class="label">工具调用</div><div class="value">{{ metrics.tool_calls ?? '-' }}</div></el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="panel">
      <template #header>按路由统计（Top 10）</template>
      <el-table :data="metrics.by_path || []" size="small" border>
        <el-table-column prop="route" label="路由" />
        <el-table-column prop="count" label="请求数" width="100" />
        <el-table-column prop="errors" label="5xx" width="80" />
        <el-table-column prop="p95" label="P95(ms)" width="100" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="panel">
      <template #header>统计口径</template>
      <ul class="notes">
        <li>数据源：每个请求落库一条 <code>request_metric</code>，与访问日志同源。</li>
        <li>错误率 = 5xx 数 / 窗口内请求数；P95 为窗口内延迟的分位值。</li>
        <li>Token 用量：P0 使用 MOCK 模型，固定上报 0（不虚报）。</li>
        <li>窗口按服务端 UTC 时间计算，与审计日志、Trace 可交叉核对。</li>
      </ul>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { apiGet } from '../../api/client'

const metrics = ref({})
const error = ref('')
const windowMinutes = ref(60)

async function load() {
  const result = await apiGet('flowai', `/monitoring/metrics?window_minutes=${windowMinutes.value}`)
  if (!result.ok) {
    error.value = `${result.code}：${result.message}`
    return
  }
  error.value = ''
  metrics.value = result.data
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
.cards {
  margin-bottom: 12px;
}
.label {
  font-size: 12px;
  color: #7c8fa3;
}
.value {
  font-size: 24px;
  font-weight: 700;
  color: #17324d;
  margin-top: 6px;
}
.panel {
  margin-bottom: 12px;
}
.notes {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: #4a5c6e;
  line-height: 1.8;
}
</style>