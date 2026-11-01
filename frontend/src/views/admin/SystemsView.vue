<template>
  <div>
    <div class="head">
      <h2>平台模块实现状态</h2>
      <div class="hint">状态来自真实实现与验收证据（docs/audit），不使用演示假数据</div>
    </div>

    <el-table :data="modules" size="small" border>
      <el-table-column prop="module" label="模块" width="170" />
      <el-table-column prop="task" label="任务编号" width="150" />
      <el-table-column prop="stage" label="阶段" width="80" />
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === '已实现' ? 'success' : 'warning'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="entry" label="入口" width="130" />
      <el-table-column prop="note" label="说明" />
    </el-table>
  </div>
</template>

<script setup>
const modules = [
  { module: '用户与角色', task: 'M02-01', stage: 'S2', status: '已实现', entry: '/admin/users', note: '四类角色、资源授权、登录限流、拒绝用例' },
  { module: 'AI 应用', task: 'M02-03', stage: 'S2', status: '已实现', entry: '/admin/applications', note: '创建/草稿测试/发布快照/版本回滚' },
  { module: '知识库', task: 'M03-01～03', stage: 'S2', status: '已实现', entry: '/admin/knowledge', note: '上传摄取、解析状态、检索引用、索引版本回滚' },
  { module: '工具中心', task: 'M04-01', stage: 'S3', status: '已实现', entry: '/admin/tools', note: '预置白名单、参数 Schema、应用授权' },
  { module: '会话与工单', task: 'M04-03 / M05-02', stage: 'S3/S4', status: '已实现', entry: '/apps/service-agent', note: '人工确认、重复风险二次确认、幂等创建' },
  { module: '监控与 Trace', task: 'M06-01', stage: 'S4', status: '已实现', entry: '/admin/monitoring', note: '按 Trace 查询、审计日志、指标与 Token 统计' },
  { module: '运行统计', task: 'M07-04', stage: 'S5', status: '已实现', entry: '/admin/stats', note: '请求量/错误率/P95/Token（口径见页面说明）' },
  { module: '模型与 Embedding', task: 'M02-02', stage: 'S2', status: '已实现', entry: '/admin/applications', note: '对话接入真实模型（DeepSeek）；向量仍为离线哈希' }
]
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
</style>