import { createRouter, createWebHistory } from 'vue-router'

import AdminLayout from '../layouts/AdminLayout.vue'
import AppLayout from '../layouts/AppLayout.vue'
import DashboardView from '../views/admin/DashboardView.vue'
import SystemsView from '../views/admin/SystemsView.vue'
import AppEntryView from '../views/apps/AppEntryView.vue'

const routes = [
  { path: '/', redirect: '/admin' },
  {
    path: '/admin',
    component: AdminLayout,
    children: [
      { path: '', name: 'admin-dashboard', component: DashboardView },
      { path: 'systems', name: 'admin-systems', component: SystemsView }
    ]
  },
  {
    path: '/apps/:slug',
    component: AppLayout,
    children: [{ path: '', name: 'app-entry', component: AppEntryView, props: true }]
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/NotFoundView.vue') }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 前端守卫只改善体验；登录态、应用授权与 RBAC 由后端独立校验（docs/06 §1，M02-01 接入）
export default router