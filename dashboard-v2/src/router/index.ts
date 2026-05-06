import { createRouter, createWebHashHistory } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import ConfigGeneralSection from '@/features/config-editor/ConfigGeneralSection.vue'
import ConfigSchedulingSection from '@/features/config-editor/ConfigSchedulingSection.vue'
import ConfigView from '@/views/ConfigView.vue'
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
          component: ConfigView,
          children: [
            {
              path: '',
              redirect: '/config/general',
            },
            {
              path: 'general',
              name: 'config-general',
              component: ConfigGeneralSection,
            },
            {
              path: 'scheduling',
              name: 'config-scheduling',
              component: ConfigSchedulingSection,
            },
            {
              path: 'playlists',
              name: 'config-playlists',
              component: RouteBoundaryView,
            },
            {
              path: 'tags',
              name: 'config-tags',
              component: RouteBoundaryView,
            },
            {
              path: 'policies',
              name: 'config-policies',
              component: RouteBoundaryView,
            },
          ],
        },
      ],
    },
  ],
})

export default router
