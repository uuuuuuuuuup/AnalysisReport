import { createRouter, createWebHashHistory } from 'vue-router'
import HomePage from './views/HomePage.vue'
import StockDetail from './views/StockDetail.vue'
import SummaryPage from './views/SummaryPage.vue'

const routes = [
  { path: '/', name: 'home', component: HomePage },
  { path: '/stock/:symbol', name: 'stock', component: StockDetail },
  { path: '/summary', name: 'summary', component: SummaryPage },
  {
    path: '/summary/:slug',
    name: 'summary-detail',
    component: () => import('./views/SummaryDetail.vue'),
  },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})