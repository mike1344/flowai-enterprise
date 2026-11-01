<template>
  <div>
    <div class="page-head">
      <h2>平台模块与开放计划</h2>
      <div class="hint">状态为真实实现状态；未实现项标注为「待开发」，不使用演示假数据</div>
    </div>

    <el-table :data="modules" size="small" border>
      <el-table-column prop="module" label="模块" width="180" />
      <el-table-column prop="task" label="任务编号" width="120" />
      <el-table-column prop="stage" label="阶段" width="90" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.status === '已就绪' ? 'success' : 'info'" size="small">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="说明" />
    </el-table>
  </div>
</template>

<script setup>
const modules = [
  { module: '运行总览', task: 'M00-02', stage: 'S0', status: '已就绪', note: '健康检查连接两个真实后端' },
  { module: '应用管理', task: 'M02-03 / M05-01', stage: 'S2/S4', status: '待开发', note: 'AI 应用 CRUD、草稿测试、发布快照' },
  { module: '知识库', task: 'M03-01～03', stage: 'S2', status: '待开发', note: '文档摄取、索引、检索与引用' },
  { module: '工具与授权', task: 'M04-01', stage: 'S3', status: '待开发', note: '预置工具白名单与参数校验' },
  { module: '会话与工单', task: 'M04-03 / M05-02', stage: 'S3/S4', status: '待开发', note: '人工确认、重复风险二次确认、幂等创建' },
  { module: '监控与 Trace', task: 'M06-01', stage: 'S4', status: '待开发', note: '跨服务 Trace、审计、基本指标' },
  { module: '用户与角色', task: 'M02-01', stage: 'S2', status: '待开发', note: '四类角色、资源授权、拒绝用例' }
]
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-head h2 {
  margin: 0;
  font-size: 18px;
  color: #17324d;
}
.hint {
  font-size: 12px;
  color: #7c8fa3;
}
</style>