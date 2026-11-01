<template>
  <div class="not-found">
    <h1>404</h1>
    <p>页面不存在，或你没有访问该应用的授权。</p>
    <el-button type="primary" @click="$router.push('/admin')">返回管理后台</el-button>
  </div>
</template>

<style scoped>
.not-found {
  max-width: 480px;
  margin: 80px auto;
  text-align: center;
  color: #17324d;
}
.not-found h1 {
  font-size: 56px;
  margin: 0;
  color: #2b6cb0;
}
.not-found p {
  color: #7c8fa3;
  margin: 12px 0 20px;
}
</style>