import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 10000,
})

api.interceptors.request.use(config => {
  // attach auth token if available (placeholder)
  // const token = ... get from store
  // if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export default api
