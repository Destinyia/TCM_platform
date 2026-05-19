export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5000'

export async function fetchJson(path, params = {}) {
  const url = new URL(path, API_BASE)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '' && value !== 'all') {
      url.searchParams.set(key, value)
    }
  })
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${url.pathname}`)
  }
  return response.json()
}

export const api = {
  summary: () => fetchJson('/api/demo/summary'),
  checkinMatrix: (params) => fetchJson('/api/demo/checkin-matrix', params),
  users: (params) => fetchJson('/api/demo/users', params),
  userTimeline: (userId) => fetchJson(`/api/demo/users/${userId}/timeline`),
  visits: (params) => fetchJson('/api/demo/visits', params),
  visitDetail: (visitId) => fetchJson(`/api/demo/visits/${visitId}`),
  assets: () => fetchJson('/api/demo/assets'),
  qualityEvents: () => fetchJson('/api/demo/quality-events'),
  datasetVersions: () => fetchJson('/api/demo/dataset-versions'),
  pulseRecords: (params) => fetchJson('/api/demo/pulse/records', params),
  pulseUserTrend: (params) => fetchJson('/api/demo/pulse/user-trend', params),
  pulseSlotStability: (params) => fetchJson('/api/demo/pulse/slot-stability', params),
  pulseCrossUser: () => fetchJson('/api/demo/pulse/cross-user'),
  pulseFeatureDrift: (params) => fetchJson('/api/demo/pulse/feature-drift', params)
}

export function apiUrl(path) {
  return new URL(path, API_BASE).toString()
}
