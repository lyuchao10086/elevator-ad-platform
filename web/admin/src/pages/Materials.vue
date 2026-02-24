<template>
  <div style="padding:16px">
    <el-row justify="space-between" align="middle" style="margin-bottom:12px">
      <el-col><h3>素材管理</h3></el-col>
      <el-col>
        <el-button type="primary" @click="openUploadDialog">上传素材</el-button>
        <div v-if="uploadLoading" style="display:inline-block; margin-left:12px; vertical-align:middle; width:220px">
          <el-progress :percentage="uploadProgress" :text-inside="false" stroke-width="10" />
        </div>
      </el-col>
    </el-row>

    <el-dialog title="上传素材并填写元数据" v-model="dialogVisible" width="720px">
      <div>
        <el-form :model="uploadForm" label-width="120px">
          <el-form-item label="广告商">
            <el-input v-model="uploadForm.advertiser" placeholder="填写广告商"></el-input>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="uploadForm.tags" placeholder=""></el-input>
          </el-form-item>
          <el-form-item label="素材类别">
            <el-select v-model="uploadForm.type" placeholder="选择类型" style="width:220px">
              <el-option label="video" value="视频" />
              <el-option label="audio" value="音频" />
              <el-option label="image" value="图片" />
              <el-option label="other" value="其他" />
            </el-select>
          </el-form-item>
          <el-form-item label="广告链接 (可选)">
            <el-input v-model="uploadForm.oss_url" placeholder="填写已有外部链接"></el-input>
          </el-form-item>
          <el-form-item label="上传文件">
            <el-upload
              ref="localUpload"
              show-file-list
              :auto-upload="false"
              @before-upload="handleBeforePick"
              @change="handleFileChange"
              :file-list="fileList"
              list-type="text">
              <el-button size="small">选择文件</el-button>
            </el-upload>
            <div style="margin-top:8px;color:#909399">文件不自动上传，点击下面的“提交并上传”完成上传。</div>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploadLoading" @click="submitUpload">提交并上传</el-button>
      </template>
    </el-dialog>

    <el-table :data="materials" style="width:100%">
      <el-table-column prop="material_id" label="素材ID" width="180"/>
      <el-table-column label="广告商" width="160">
        <template #default="{ row }">
          {{ row.advertiser || row.ad_id || (row.extra && row.extra.raw && (row.extra.raw.advertiser || row.extra.raw.ad_id)) || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="file_name" label="广告名"/>
      <el-table-column prop="oss_url" label="广告链接" width="240">
        <template #default="{ row }">
          <a :href="row.oss_url" target="_blank">{{ row.oss_url }}</a>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120"/>
      <el-table-column prop="tags" label="备注" width="200">
        <template #default="{ row }">{{ formatTags(row.tags) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button type="text" size="small" @click="onPreview(row)">预览</el-button>
          <el-button type="danger" size="small" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import materialsApi from '../api/materials'

// optional: use wrapper api if available

export default {
  setup(){
    const materials = ref([])
    const uploadAction = (api.defaults && api.defaults.baseURL ? api.defaults.baseURL : (import.meta.env.VITE_API_URL || '')) + '/v1/materials/upload'
    const uploadLoading = ref(false)
    const uploadProgress = ref(0)

    const dialogVisible = ref(false)
    const uploadForm = ref({ advertiser: '', tags: '', type: 'video', duration_sec: null, oss_url: '', uploader_id: 'web-admin' })
    const fileList = ref([])
    const pickedFile = ref(null)

    function formatSize(n){
      if(!n && n !== 0) return ''
      const kb = 1024
      if(n < kb) return n + ' B'
      if(n < kb*kb) return (n/kb).toFixed(1) + ' KB'
      if(n < kb*kb*kb) return (n/(kb*kb)).toFixed(1) + ' MB'
      return (n/(kb*kb*kb)).toFixed(1) + ' GB'
    }

    function formatDate(s){
      if(!s) return ''
      try{
        const d = new Date(s)
        if(isNaN(d)) return s
        return d.toLocaleString()
      }catch(e){ return s }
    }

    function formatTags(t){
      if(!t) return ''
      if(Array.isArray(t)) return t.join(', ')
      try{ return JSON.stringify(t) }catch(e){ return String(t) }
    }

    async function fetch(){
      try{
        const data = await materialsApi.listMaterials()
        materials.value = data?.items || data || []
      }catch(e){
        console.warn('fetch materials failed, using fallback', e)
        // fallback mock
        materials.value = [
          { material_id: 'M_001', advertiser: 'adv_101', file_name: 'nike_shoe.mp4', oss_url: 'https://oss.example.com/ads/nike_shoe.mp4', size_bytes: 20485760, status: 'ready', created_at: '2026-01-29T16:09:09Z', updated_at: '2026-01-29T16:09:09Z', tags: ['示例'] }
        ]
      }
    }

    function beforeUpload(file){
      // check file size (e.g., <= 200MB) and basic type if desired
      const max = 200 * 1024 * 1024
      if(file.size > max){
        ElMessage.error('文件太大，最大支持 200MB')
        return false
      }
      return true
    }

    function openUploadDialog(){
      console.debug('openUploadDialog called')
      uploadForm.value = { advertiser: '', tags: '', type: 'video', duration_sec: null, oss_url: '', uploader_id: 'web-admin' }
      fileList.value = []
      pickedFile.value = null
      dialogVisible.value = true
    }

    function handleBeforePick(file){
      // reuse validation
      return beforeUpload(file)
    }

    function handleFileChange(file, fileListArg){
      // file is the single file obj from element-plus; keep reference to raw file
      // ElementPlus file.raw is the actual File/Blob
      console.debug('handleFileChange', file, fileListArg)
      pickedFile.value = file.raw || null
      fileList.value = fileListArg
      // prefill filename if empty
      if(pickedFile.value && !uploadForm.value.oss_url){
        uploadForm.value.file_name = pickedFile.value.name
      }
    }

    function onUploadSuccess(res, file){
      ElMessage.success('上传成功')
      uploadProgress.value = 100
      uploadLoading.value = false
      // refresh list
      fetch()
    }

    function onUploadError(err, file){
      console.error('upload error', err)
      ElMessage.error('上传失败')
      uploadLoading.value = false
      uploadProgress.value = 0
    }

    function onUploadProgress(e){
      if(e && e.percent != null){
        uploadProgress.value = Math.round(e.percent)
      }
      uploadLoading.value = true
    }

    async function submitUpload(){
      if(!pickedFile.value){
        ElMessage.error('请先选择要上传的文件')
        return
      }
      try{
        console.debug('submitUpload starting')
        uploadLoading.value = true
        uploadProgress.value = 0
        const fd = new FormData()
        fd.append('file', pickedFile.value)
        if(uploadForm.value.advertiser) fd.append('advertiser', uploadForm.value.advertiser)
        if(uploadForm.value.uploader_id) fd.append('uploader_id', uploadForm.value.uploader_id)
        if(uploadForm.value.tags) fd.append('tags', uploadForm.value.tags)
        if(uploadForm.value.type) fd.append('type', uploadForm.value.type)
        if(uploadForm.value.duration_sec != null) fd.append('duration_sec', String(uploadForm.value.duration_sec))
        if(uploadForm.value.oss_url) fd.append('oss_url', uploadForm.value.oss_url)
        if(uploadForm.value.file_name) fd.append('file_name', uploadForm.value.file_name)

        const res = await materialsApi.uploadMaterial(fd, {
          onUploadProgress: (evt) => onUploadProgress({ percent: (evt.loaded/evt.total*100) })
        })
        console.debug('submitUpload response', res)

        onUploadSuccess(res, pickedFile.value)
        dialogVisible.value = false
      }catch(e){
        console.error('upload failed', e)
        onUploadError(e)
      }finally{
        uploadLoading.value = false
      }
    }

    function onPreview(row){
      window.open(row.oss_url || '#')
    }
    // 转码功能已移除；保留占位以便未来扩展
    async function onDelete(row){
      try{
        await materialsApi.deleteMaterial(row.material_id)
        ElMessage.success('删除成功')
        fetch()
      }catch(e){ ElMessage.error('删除失败') }
    }

    onMounted(fetch)
    return { materials, uploadAction, beforeUpload, onUploadSuccess, onUploadError, onUploadProgress, uploadLoading, uploadProgress, dialogVisible, uploadForm, fileList, openUploadDialog, handleBeforePick, handleFileChange, submitUpload, onPreview, onDelete, formatSize, formatDate, formatTags }
  }
}
</script>
