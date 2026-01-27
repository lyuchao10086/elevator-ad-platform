import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../pages/Dashboard.vue'
import DeviceList from '../pages/DeviceList.vue'
import Commands from '../pages/Commands.vue'
import Materials from '../pages/Materials.vue'
import Campaigns from '../pages/Campaigns.vue'

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/devices', name: 'DeviceList', component: DeviceList },
  { path: '/commands', name: 'Commands', component: Commands },
  { path: '/materials', name: 'Materials', component: Materials },
  { path: '/campaigns', name: 'Campaigns', component: Campaigns },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
