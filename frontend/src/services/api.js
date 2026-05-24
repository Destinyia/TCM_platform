function defaultApiBase() {
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:5000`
  }
  return 'http://localhost:5000'
}

export const API_BASE = import.meta.env.VITE_API_BASE || defaultApiBase()

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
  pulseFeatureDrift: (params) => fetchJson('/api/demo/pulse/feature-drift', params),
  pulsePhase1Summary: () => fetchJson('/api/pulse/analysis/phase1-summary'),
  pulseUserSummary: (params) => fetchJson('/api/pulse/analysis/user-summary', params),
  getPulseUsers: (params) => fetchJson('/api/demo/users', params),
  getPulseUserSummary: (userId) => fetchJson('/api/pulse/analysis/user-summary', { user_id: userId }),
  getPulseUserRecords: (userId, filters = {}) => fetchJson('/api/demo/pulse/records', { user_id: userId, include_suspicious: true, ...filters }),
  getPulseRecordDetail: (userId, recordId) => fetchJson('/api/demo/pulse/records', { user_id: userId, include_suspicious: true, record_id: recordId }),
  getPulseFeatureSummary: (measurementId) => fetchJson('/api/pulse/analysis/feature-summary', { measurement_id: measurementId }),
  getPulsePeriodConsistency: (userId, recordId) => fetchJson('/api/pulse/analysis/period-consistency', { user_id: userId, record_id: recordId }),
  getPulseDeviceFitOverview: (params) => fetchJson('/api/pulse/analysis/device-fit-overview', params),
  getPulsePersonalBaseline: (userId) => fetchJson('/api/pulse/analysis/personal-baseline', { user_id: userId })
}

export function apiUrl(path) {
  return new URL(path, API_BASE).toString()
}
