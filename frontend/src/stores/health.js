import { defineStore } from 'pinia'

import { apiGet } from '../api/client'

// 健康检查状态（M00-02）：真实调用两个后端，不做假数据
export const useHealthStore = defineStore('health', {
  state: () => ({
    loading: false,
    error: '',
    flowai: null,
    industrial: null,
    checkedAt: ''
  }),
  getters: {
    rows: (state) =>
      [
        { name: 'flowai-api', port: 8001, result: state.flowai },
        { name: 'industrial-api', port: 8002, result: state.industrial }
      ].filter(Boolean),
    allHealthy: (state) =>
      Boolean(state.flowai?.ok) && Boolean(state.industrial?.ok)
  },
  actions: {
    async refresh() {
      this.loading = true
      this.error = ''
      try {
        const [flowai, industrial] = await Promise.all([
          apiGet('flowai', '/health'),
          apiGet('industrial', '/health')
        ])
        this.flowai = flowai
        this.industrial = industrial
        this.checkedAt = new Date().toLocaleTimeString()
      } catch (error) {
        this.error = String(error)
      } finally {
        this.loading = false
      }
    }
  }
})