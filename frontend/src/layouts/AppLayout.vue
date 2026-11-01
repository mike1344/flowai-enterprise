<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-title">{{ slug }}</div>
      <div class="app-meta">独立应用布局 · 会话、引用与工单确认已启用</div>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const slug = computed(() => String(route.params.slug || 'demo-app'))
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #f7f9fc;
}
.app-header {
  background: #fff;
  border-bottom: 1px solid #e6ecf3;
  padding: 16px 24px;
}
.app-title {
  font-size: 18px;
  font-weight: 700;
  color: #17324d;
}
.app-meta {
  font-size: 12px;
  color: #7c8fa3;
  margin-top: 4px;
}
.app-main {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}
</style>