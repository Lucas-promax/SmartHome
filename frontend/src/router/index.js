import { createRouter, createWebHashHistory } from 'vue-router'

// 懒加载页面组件
const Dashboard = () => import('../views/Dashboard.vue')
const AiRecognition = () => import('../views/AiRecognition.vue')
const DataAnalysis = () => import('../views/DataAnalysis.vue')
const PersonnelManagement = () => import('../views/PersonnelManagement.vue')
const SystemLogs = () => import('../views/SystemLogs.vue')
const SmartAssistant = () => import('../views/SmartAssistant.vue')
const SystemSettings = () => import('../views/SystemSettings.vue')

const routes = [
  {
    path: '/',
    redirect: '/dashboard'
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: Dashboard,
    meta: { title: '首页看板', icon: 'Odometer' }
  },
  {
    path: '/ai-recognition',
    name: 'AiRecognition',
    component: AiRecognition,
    meta: { title: 'AI识别', icon: 'View' }
  },
  {
    path: '/data-analysis',
    name: 'DataAnalysis',
    component: DataAnalysis,
    meta: { title: '数据分析', icon: 'TrendCharts' }
  },
  {
    path: '/personnel',
    name: 'PersonnelManagement',
    component: PersonnelManagement,
    meta: { title: '授权管理', icon: 'User' }
  },
  {
    path: '/logs',
    name: 'SystemLogs',
    component: SystemLogs,
    meta: { title: '系统日志', icon: 'Document' }
  },
  {
    path: '/assistant',
    name: 'SmartAssistant',
    component: SmartAssistant,
    meta: { title: '智能助手', icon: 'ChatDotRound' }
  },
  {
    path: '/settings',
    name: 'SystemSettings',
    component: SystemSettings,
    meta: { title: '系统配置', icon: 'Setting' }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
