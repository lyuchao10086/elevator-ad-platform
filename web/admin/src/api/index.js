import axios from 'axios'

const timeoutMs = Number(import.meta.env.VITE_API_TIMEOUT_MS || 30000)

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: Number.isFinite(timeoutMs) ? timeoutMs : 30000,
})

api.interceptors.request.use(config => {
  // attach auth token if available (placeholder)
  // const token = ... get from store
  // if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export default api
