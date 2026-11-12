import axios from 'axios'

const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api'

export const api = axios.create({
  baseURL: BASE,
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('forge_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('forge_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// Auth
export const authApi = {
  register: (email: string, password: string) =>
    api.post('/auth/register', { email, password }),
  login: (email: string, password: string) => {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)
    return api.post('/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },
  me: () => api.get('/auth/me'),
}

// Projects
export const projectsApi = {
  list: () => api.get('/projects/'),
  create: (name: string, instrument: string, timeframe: string, description?: string) =>
    api.post('/projects/', { name, instrument, timeframe, description }),
  get: (id: string) => api.get(`/projects/${id}`),
  delete: (id: string) => api.delete(`/projects/${id}`),
}

// Pipeline
export const pipelineApi = {
  status: (projectId: string) =>
    api.get(`/projects/${projectId}/pipeline/status`),
  skipWarning: (projectId: string, stage: number) =>
    api.get(`/projects/${projectId}/pipeline/${stage}/skip-warning`),
  skip: (projectId: string, stage: number, confirmed = false) =>
    api.post(`/projects/${projectId}/pipeline/${stage}/skip`, { confirmed }),

  // Hypothesis
  chat: (projectId: string, message: string) =>
    api.post(`/projects/${projectId}/pipeline/hypothesis/chat`, { message }),

  // Code
  generateCode: (projectId: string) =>
    api.post(`/projects/${projectId}/pipeline/code/generate`),
  scanCode: (projectId: string, versionId: string) =>
    api.post(`/projects/${projectId}/pipeline/code/${versionId}/scan`),
  activateCode: (projectId: string, versionId: string) =>
    api.post(`/projects/${projectId}/pipeline/code/${versionId}/activate`),
  listVersions: (projectId: string) =>
    api.get(`/projects/${projectId}/pipeline/code/versions`),

  // Split
  splitRecommendation: (projectId: string) =>
    api.get(`/projects/${projectId}/pipeline/split/recommendation`),
  lockSplit: (projectId: string, splitData: object) =>
    api.post(`/projects/${projectId}/pipeline/split/lock`, splitData),

  // Development
  runDevelopment: (projectId: string) =>
    api.post(`/projects/${projectId}/pipeline/development/run`),
  devJobStatus: (projectId: string, jobId: string) =>
    api.get(`/projects/${projectId}/pipeline/development/jobs/${jobId}`),

  // Validation
  runValidation: (projectId: string) =>
    api.post(`/projects/${projectId}/pipeline/validation/run`),
  validationJobStatus: (projectId: string, jobId: string) =>
    api.get(`/projects/${projectId}/pipeline/validation/jobs/${jobId}`),
}

// Reports
export const reportsApi = {
  get: (projectId: string) =>
    api.get(`/reports/?project_id=${projectId}`),
}

// Account setup
export const accountApi = {
  propFirms: () => api.get('/account/prop-firms'),
  rankPropFirms: (projectId: string) =>
    api.post('/account/prop-firms/rank', { project_id: projectId }),
  kellyTable: (projectId: string, accountSize: number, maxDd = 0.2) =>
    api.post('/account/live/kelly-table', {
      project_id: projectId,
      account_size: accountSize,
      max_acceptable_dd_pct: maxDd,
    }),
  setAccountType: (type: 'prop_firm' | 'live') =>
    api.put('/account/type', { account_type: type }),
}

// Papers
export const papersApi = {
  search: (query: string) => api.post('/papers/search', { query }),
  jobStatus: (taskId: string) => api.get(`/papers/job/${taskId}`),
}
