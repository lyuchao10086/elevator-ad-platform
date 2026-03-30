import api from './index'

export async function listCampaigns(params) {
  const r = await api.get('/v1/campaigns', { params })
  return r.data
}

export async function getCampaign(campaignId) {
  const r = await api.get(`/v1/campaigns/${campaignId}`)
  return r.data
}

export async function deleteCampaign(campaignId) {
  const r = await api.delete(`/v1/campaigns/${campaignId}`)
  return r.data
}

export async function getScheduleConfig(campaignId) {
  const r = await api.get(`/v1/campaigns/${campaignId}/schedule-config`)
  return r.data
}

export async function getEdgeSchedule(campaignId) {
  const r = await api.get(`/v1/campaigns/${campaignId}/edge-schedule`)
  return r.data
}

export async function createCampaignStrategy(payload) {
  const r = await api.post('/v1/campaigns/strategy', payload)
  return r.data
}

export async function updateCampaignStrategy(campaignId, payload) {
  const r = await api.put(`/v1/campaigns/${campaignId}/strategy`, payload)
  return r.data
}

export async function publishCampaign(campaignId) {
  const r = await api.post(`/v1/campaigns/${campaignId}/publish`)
  return r.data
}

export async function listPublishLogs(campaignId, params) {
  const r = await api.get(`/v1/campaigns/${campaignId}/publish-logs`, { params })
  return r.data
}

export async function retryFailed(campaignId) {
  const r = await api.post(`/v1/campaigns/${campaignId}/retry-failed`)
  return r.data
}

export async function listVersions(campaignId, params) {
  const r = await api.get(`/v1/campaigns/${campaignId}/versions`, { params })
  return r.data
}

export async function rollbackCampaign(campaignId, payload) {
  const r = await api.post(`/v1/campaigns/${campaignId}/rollback`, payload)
  return r.data
}

export async function listDevices(params) {
  const r = await api.get('/v1/devices', { params })
  return r.data
}

export default {
  listCampaigns,
  getCampaign,
  deleteCampaign,
  getScheduleConfig,
  getEdgeSchedule,
  createCampaignStrategy,
  updateCampaignStrategy,
  publishCampaign,
  listPublishLogs,
  retryFailed,
  listVersions,
  rollbackCampaign,
  listDevices,
}
