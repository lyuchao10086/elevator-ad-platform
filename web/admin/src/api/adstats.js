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
  return api.get(`/v1/ad_stats/ads/${encodeURIComponent(ad_file_name)}`)
}

export default { devicesSummary, deviceDetail, adsSummary, adDetail }
