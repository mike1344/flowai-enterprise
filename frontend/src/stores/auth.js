import { defineStore } from 'pinia'

import { apiGet, apiPost, setCsrfToken } from '../api/client'

// 管理端登录态：服务端会话 + CSRF 令牌（ADR-013）
export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    roles: [],
    permissions: [],
    loading: false,
    error: ''
  }),
  getters: {
    loggedIn: (state) => Boolean(state.user),
    can: (state) => (code) => state.permissions.includes(code)
  },
  actions: {
    async login(username, password) {
      this.loading = true
      this.error = ''
      try {
        const result = await apiPost('flowai', '/auth/login', { body: { username, password } })
        if (!result.ok) {
          this.error = result.message || '登录失败'
          return false
        }
        setCsrfToken(result.data.csrf_token)
        this.user = result.data.user
        this.roles = result.data.roles || []
        this.permissions = result.data.permissions || []
        return true
      } finally {
        this.loading = false
      }
    },
    async fetchMe() {
      const result = await apiGet('flowai', '/auth/me')
      if (!result.ok) {
        this.user = null
        return false
      }
      this.user = {
        id: result.data.id,
        username: result.data.username,
        display_name: result.data.display_name
      }
      this.roles = result.data.roles || []
      this.permissions = result.data.permissions || []
      if (result.data.csrf_token) setCsrfToken(result.data.csrf_token)
      return true
    },
    async logout() {
      await apiPost('flowai', '/auth/logout')
      setCsrfToken('')
      this.user = null
      this.roles = []
      this.permissions = []
    }
  }
})