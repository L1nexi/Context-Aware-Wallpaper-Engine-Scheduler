import { createRouter, createWebHashHistory } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import DashboardView from '@/views/DashboardView.vue'
import RouteBoundaryView from '@/views/RouteBoundaryView.vue'

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
        {
          path: 'history',
          name: 'history',
          component: RouteBoundaryView,
        },
        {
          path: 'config',
          redirect: '/config/general',
        },
        {
          path: 'config/general',
          name: 'config-general',
          component: RouteBoundaryView,
        },
        {
          path: 'config/scheduling',
          name: 'config-scheduling',
          component: RouteBoundaryView,
        },
        {
          path: 'config/playlists',
          name: 'config-playlists',
          component: RouteBoundaryView,
        },
        {
          path: 'config/tags',
          name: 'config-tags',
          component: RouteBoundaryView,
        },
        {
          path: 'config/policies',
          name: 'config-policies',
          component: RouteBoundaryView,
        },
      ],
    },
  ],
})

export default router
