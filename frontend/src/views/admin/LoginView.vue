<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="never">
      <h2>FlowAI 管理后台</h2>
      <p class="hint">使用平台账号登录；未授权应用不会出现在列表。</p>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" autocomplete="username" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="口令" show-password autocomplete="current-password" />
        </el-form-item>
        <el-alert v-if="auth.error" :title="auth.error" type="error" :closable="false" show-icon />
        <el-button type="primary" class="submit" :loading="auth.loading" @click="submit">登录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref('admin')
const password = ref('')

async function submit() {
  const ok = await auth.login(username.value, password.value)
  if (ok) router.push('/admin')
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f4f7fb;
}
.login-card {
  width: 360px;
  border-radius: 12px;
}
h2 {
  margin: 0 0 4px;
  color: #17324d;
}
.hint {
  font-size: 12px;
  color: #7c8fa3;
  margin: 0 0 16px;
}
.submit {
  width: 100%;
  margin-top: 8px;
}
</style>