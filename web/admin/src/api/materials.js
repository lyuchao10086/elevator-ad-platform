import api from './index'

export async function listMaterials(params){
  const r = await api.get('/v1/materials', { params })
  return r.data
}

export async function uploadMaterial(formData, config){
  // config can include onUploadProgress
  const r = await api.post('/v1/materials/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    ...config,
  })
  return r.data
}

export async function deleteMaterial(materialId){
  const r = await api.delete(`/v1/materials/${materialId}`)
  return r.data
}

export default { listMaterials, uploadMaterial, deleteMaterial }
