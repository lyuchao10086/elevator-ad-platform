import api from './index'

export async function listAdLogs(params){
  // GET /api/v1/ad_logs
  return api.get('/v1/ad_logs', { params })
}

export async function getAdLog(id){
  return api.get(`/v1/ad_logs/${id}`)
}

export default { listAdLogs, getAdLog }
