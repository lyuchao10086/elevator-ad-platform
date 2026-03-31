import api from './index'

export async function devicesSummary(){
  return api.get('/v1/ad_stats/devices')
}

export async function deviceDetail(device_id){
  return api.get(`/v1/ad_stats/devices/${encodeURIComponent(device_id)}`)
}

export async function adsSummary(){
  return api.get('/v1/ad_stats/ads')
}

export async function adDetail(ad_file_name){
  return api.get('/v1/ad_stats/ads/detail', { params: { ad_file_name } })
}

export async function advertisersList(){
  return api.get('/v1/ad_stats/advertisers')
}

export async function billingReport(client_id, month){
  return api.get('/v1/ad_stats/billing_report', { params: { client_id, month } })
}

export default { devicesSummary, deviceDetail, adsSummary, adDetail, advertisersList, billingReport }
