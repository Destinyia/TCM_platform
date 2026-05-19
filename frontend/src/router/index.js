import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    children: [
      { path: '', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
      { path: 'checkin-matrix', name: 'CheckinMatrix', component: () => import('../views/CheckinMatrix.vue') },
      { path: 'patients', name: 'Patients', component: () => import('../views/Patients.vue') },
      { path: 'patients/:id', name: 'PatientDetail', component: () => import('../views/PatientDetail.vue') },
      { path: 'examinations', name: 'Examinations', component: () => import('../views/Examinations.vue') },
      { path: 'pulse-analysis', name: 'PulseAnalysis', component: () => import('../views/PulseAnalysis.vue') },
      { path: 'import', name: 'Import', component: () => import('../views/Import.vue') },
      { path: 'export', name: 'Export', component: () => import('../views/Export.vue') }
    ]
  }
]

export default createRouter({
  history: createWebHistory(),
  routes
})
