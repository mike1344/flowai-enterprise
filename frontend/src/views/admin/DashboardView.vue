<template>
  <div>
    <div class="page-head">
      <h2>运行总览</h2>
      <div class="actions">
        <span v-if="health.checkedAt" class="checked-at">最近检查：{{ health.checkedAt }}</span>
        <el-button type="primary" :loading="health.loading" @click="health.refresh()">重新检查</el-button>
      </div>
    </div>

    <el-alert
      v-if="health.error"
      type="error"
      :closable="false"
      title="无法获取服务状态"
      :description="health.error"
      show-icon
    />

    <el-row :gutter="16" class="cards">
      <el-col v-for="item in health.rows" :key="item.name" :xs="24" :md="12">
        <el-card shadow="never" class="card">
          <div class="card-head">
            <span class="name">{{ item.name }}</span>
            <el-tag :type="item.result.ok ? 'success' : 'danger'" effect="dark">
              {{ item.result.ok ? '可用' : '异常' }}
            </el-tag>
          </div>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="端口">{{ item.port }}</el-descriptions-item>
            <el-descriptions-item label="HTTP">{{ item.result.status || '无响应' }}</el-descriptions-item>
            <el-descriptions-item label="服务状态">
              {{ item.result.data?.status || '未知' }}
            </el-descriptions-item>
            <el-descriptions-item label="版本">
              {{ item.result.data?.version || '未知' }}
            </el-descriptions-item>
            <el-descriptions-item label="Trace ID">
              <code class="trace">{{ item.result.traceId }}</code>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!health.loading && health.rows.length === 0" description="尚未取得服务状态" />

    <el-card shadow="never" class="card note">
      <template #header>阶段说明</template>
      <p>
        当前处于 <b>S0 基础环境</b>：三端骨架与健康接口已就绪。业务页面（应用配置、知识库、
        工具授权、监控）将按 M02～M06 顺序开放，未实现的功能不会以假数据展示。
      </p>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'

import { useHealthStore } from '../../stores/health'

const health = useHealthStore()

onMounted(() => {
  health.refresh()
})
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-head h2 {
  margin: 0;
  font-size: 18px;
  color: #17324d;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.checked-at {
  font-size: 12px;
  color: #7c8fa3;
}
.cards {
  margin-bottom: 8px;
}
.card {
  border-radius: 10px;
  margin-bottom: 16px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.card-head .name {
  font-weight: 700;
  color: #17324d;
}
.trace {
  font-size: 12px;
  color: #2b6cb0;
  word-break: break-all;
}
.note p {
  margin: 0;
  color: #4a5c6e;
  line-height: 1.7;
  font-size: 13px;
}
</style>