<template>
  <div>
    <div class="head">
      <h2>用户与角色</h2>
      <div class="actions">
        <el-input v-model="form.username" placeholder="用户名" size="small" style="width: 130px" />
        <el-input v-model="form.display_name" placeholder="显示名" size="small" style="width: 130px" />
        <el-input v-model="form.password" type="password" placeholder="初始口令（≥8位）" size="small" style="width: 160px" />
        <el-button type="primary" size="small" :loading="saving" @click="createUser">新建用户</el-button>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <el-table :data="users" size="small" border v-loading="loading">
      <el-table-column prop="username" label="用户名" width="140" />
      <el-table-column prop="display_name" label="显示名" width="140" />
      <el-table-column label="角色" width="220">
        <template #default="{ row }">
          <el-tag v-for="role in row.roles" :key="role" size="small" class="tag">{{ role }}</el-tag>
          <span v-if="!row.roles.length" class="muted">未分配</span>
        </template>
      </el-table-column>
      <el-table-column label="权限数" width="90">
        <template #default="{ row }">{{ row.permissions.length }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="260">
        <template #default="{ row }">
          <el-select
            size="small"
            placeholder="分配角色"
            style="width: 150px"
            @change="(role) => assignRole(row.id, role)"
          >
            <el-option v-for="role in roles" :key="role" :label="role" :value="role" />
          </el-select>
          <el-button size="small" @click="showGrants(row)">授权</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="grantDialog" :title="`资源授权 · ${grantUser?.username || ''}`" width="520px">
      <el-table :data="grants" size="small" border>
        <el-table-column prop="resource_type" label="资源类型" width="150" />
        <el-table-column prop="resource_id" label="资源 ID" width="100" />
        <el-table-column prop="permission" label="权限" width="100" />
      </el-table>
      <div class="grant-form">
        <el-select v-model="grantForm.resource_type" size="small" style="width: 150px">
          <el-option label="APPLICATION" value="APPLICATION" />
          <el-option label="KNOWLEDGE_BASE" value="KNOWLEDGE_BASE" />
        </el-select>
        <el-input-number v-model="grantForm.resource_id" :min="1" size="small" style="width: 110px" />
        <el-select v-model="grantForm.permission" size="small" style="width: 120px">
          <el-option label="READ" value="READ" />
          <el-option label="USE" value="USE" />
          <el-option label="MANAGE" value="MANAGE" />
        </el-select>
        <el-button size="small" type="primary" @click="addGrant">添加</el-button>
      </div>
      <p class="muted">提示：平台管理员不自动获得客户业务数据权限；资源授权只控制本平台内的应用/知识库访问。</p>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { apiGet, apiPost } from '../../api/client'

const users = ref([])
const roles = ['PLATFORM_ADMIN', 'APP_ADMIN', 'BUSINESS_USER', 'END_USER']
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const form = reactive({ username: '', display_name: '', password: '' })
const grantDialog = ref(false)
const grantUser = ref(null)
const grants = ref([])
const grantForm = reactive({ resource_type: 'APPLICATION', resource_id: 1, permission: 'USE' })

async function load() {
  loading.value = true
  try {
    const result = await apiGet('flowai', '/auth/users')
    if (!result.ok) {
      error.value = `${result.code}：${result.message}`
      return
    }
    users.value = result.data.items || []
  } finally {
    loading.value = false
  }
}

async function createUser() {
  saving.value = true
  error.value = ''
  try {
    const result = await apiPost('flowai', '/auth/users', { body: { ...form } })
    if (!result.ok) {
      error.value = `${result.code}：${result.message}`
      return
    }
    form.username = ''
    form.display_name = ''
    form.password = ''
    await load()
  } finally {
    saving.value = false
  }
}

async function assignRole(userId, roleCode) {
  const result = await apiPost('flowai', `/auth/users/${userId}/roles`, { body: { role_code: roleCode } })
  if (!result.ok) error.value = `${result.code}：${result.message}`
  await load()
}

async function showGrants(user) {
  grantUser.value = user
  grantDialog.value = true
  const result = await apiGet('flowai', `/auth/grants/${user.id}`)
  grants.value = result.data.items || []
}

async function addGrant() {
  if (!grantUser.value) return
  const result = await apiPost('flowai', '/auth/grants', {
    body: { user_id: grantUser.value.id, ...grantForm }
  })
  if (!result.ok) error.value = `${result.code}：${result.message}`
  await showGrants(grantUser.value)
}

onMounted(load)
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.head h2 {
  margin: 0;
  font-size: 18px;
  color: #17324d;
}
.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.tag {
  margin-right: 4px;
}
.muted {
  font-size: 12px;
  color: #9aa9b8;
}
.grant-form {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  align-items: center;
  flex-wrap: wrap;
}
</style>