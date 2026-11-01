import { createRouter, createWebHistory } from 'vue-router'

import AdminLayout from '../layouts/AdminLayout.vue'
import AppLayout from '../layouts/AppLayout.vue'
import DashboardView from '../views/admin/DashboardView.vue'
import ApplicationsView from '../views/admin/ApplicationsView.vue'
import KnowledgeView from '../views/admin/KnowledgeView.vue'
import LoginView from '../views/admin/LoginView.vue'
import ModelsView from '../views/admin/ModelsView.vue'
import MonitoringView from '../views/admin/MonitoringView.vue'
import StatsView from '../views/admin/StatsView.vue'
import ToolsView from '../views/admin/ToolsView.vue'
import UsersView from '../views/admin/UsersView.vue'
import SystemsView from '../views/admin/SystemsView.vue'
import AppChatView from '../views/apps/AppChatView.vue'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', redirect: '/admin' },
  { path: '/login', name: 'login', component: LoginView },
  {
    path: '/admin',
    component: AdminLayout,
    children: [
      { path: '', name: 'admin-dashboard', component: DashboardView },
      { path: 'applications', name: 'admin-applications', component: ApplicationsView },
      { path: 'knowledge', name: 'admin-knowledge', component: KnowledgeView },
      { path: 'stats', name: 'admin-stats', component: StatsView },
      { path: 'models', name: 'admin-models', component: ModelsView },
      { path: 'tools', name: 'admin-tools', component: ToolsView },
      { path: 'users', name: 'admin-users', component: UsersView },
      { path: 'monitoring', name: 'admin-monitoring', component: MonitoringView },
      { path: 'systems', name: 'admin-systems', component: SystemsView }
    ]
  },
  {
    path: '/apps/:slug',
    component: AppLayout,
    children: [{ path: '', name: 'app-chat', component: AppChatView, props: true }]
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/NotFoundView.vue') }
]

const router = createRouter({ history: createWebHistory(), routes })

// 前端守卫仅改善体验；鉴权与资源授权由后端独立校验（docs/06 §1）
router.beforeEach(async (to) => {
  if (to.name === 'login') return true
  const auth = useAuthStore()
  if (auth.loggedIn) return true
  const restored = await auth.fetchMe()
  if (restored) return true
  return { name: 'login', query: { redirect: to.fullPath } }
})

export default router