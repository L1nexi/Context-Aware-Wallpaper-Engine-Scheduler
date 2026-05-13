import { createRouter, createWebHashHistory } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import DashboardView from '@/views/DashboardView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      component: AppShell,
      children: [
        {
          path: '',
          redirect: '/dashboard',
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: DashboardView,
        },
      ],
    },
  ],
})

export default router
