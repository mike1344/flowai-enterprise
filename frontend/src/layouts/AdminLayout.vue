<template>
  <el-container class="admin-shell">
    <el-aside width="220px" class="admin-aside">
      <div class="brand">
        <span class="brand-dot" />
        FlowAI 管理后台
      </div>
      <el-menu :default-active="activePath" router class="admin-menu">
        <el-menu-item index="/admin">运行总览</el-menu-item>
        <el-menu-item index="/admin/systems">平台模块</el-menu-item>
      </el-menu>
      <div class="aside-hint">P0 逐步开放：应用 / 知识库 / 工具 / 用户 / 监控</div>
    </el-aside>
    <el-container>
      <el-header class="admin-header">
        <div class="title">FlowAI Enterprise V1.2</div>
        <div class="subtitle">单仓库 · 双后端 · 单前端 · 阶段 S0</div>
      </el-header>
      <el-main class="admin-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activePath = computed(() => route.path)
</script>

<style scoped>
.admin-shell {
  height: 100vh;
}
.admin-aside {
  background: #102a43;
  color: #e6eef7;
  display: flex;
  flex-direction: column;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  padding: 18px 16px;
  color: #fff;
  letter-spacing: 0.5px;
}
.brand-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #35c491;
  box-shadow: 0 0 8px #35c491;
}
.admin-menu {
  border-right: none;
  background: transparent;
  --el-menu-bg-color: transparent;
  --el-menu-text-color: #c9d8e8;
  --el-menu-hover-bg-color: #1b3a57;
  --el-menu-active-color: #fff;
}
.aside-hint {
  margin-top: auto;
  padding: 14px 16px;
  font-size: 12px;
  color: #8aa3ba;
  line-height: 1.6;
}
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e6ecf3;
}
.admin-header .title {
  font-weight: 700;
  color: #123c65;
}
.admin-header .subtitle {
  font-size: 12px;
  color: #7c8fa3;
}
.admin-main {
  background: #f4f7fb;
}
</style>