<template>
  <div style="padding:16px">
    <el-row justify="space-between" align="middle" style="margin-bottom:12px">
      <el-col><h3>素材管理</h3></el-col>
      <el-col>
        <el-upload
          :action="uploadAction"
          :show-file-list="false"
          :before-upload="beforeUpload"
          @success="onUploadSuccess">
          <el-button type="primary">上传素材</el-button>
        </el-upload>
      </el-col>
    </el-row>

    <el-table :data="materials" style="width:100%">
      <el-table-column prop="material_id" label="素材ID" width="220"/>
      <el-table-column prop="ad_id" label="广告ID"/>
      <el-table-column prop="duration_sec" label="时长(s)" width="100"/>
      <el-table-column prop="size_bytes" label="大小" width="120"/>
      <el-table-column prop="status" label="状态" width="140"/>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button type="text" size="small" @click="onPreview(row)">预览</el-button>
          <el-button type="text" size="small" @click="onTranscode(row)">转码</el-button>
          <el-button type="danger" size="small" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import api from '../api'

export default {
  setup(){
    const materials = ref([])
    const uploadAction = import.meta.env.VITE_API_URL + '/materials/upload'

    async function fetch(){
      try{
        const r = await api.get('/v1/materials')
        materials.value = r.data?.items || []
      }catch(e){
        // fallback mock
        materials.value = [
          { material_id: 'M_001', ad_id: 'AD_NIKE_01', duration_sec: 15, size_bytes: 10485760, status: 'ready' }
        ]
      }
    }

    function beforeUpload(file){
      // optional: check file type/size
      return true
    }
    function onUploadSuccess(res, file){
      this.$message.success('上传成功')
      fetch()
    }

    function onPreview(row){
      window.open(row.oss_url || '#')
    }
    async function onTranscode(row){
      try{
        await api.post('/v1/materials/' + row.material_id + '/transcode')
        this.$message.success('已触发转码')
      }catch(e){ console.warn(e); this.$message.error('触发转码失败') }
    }
    async function onDelete(row){
      try{
        await api.delete('/v1/materials/' + row.material_id)
        this.$message.success('删除成功')
        fetch()
      }catch(e){ this.$message.error('删除失败') }
    }

    onMounted(fetch)
    return { materials, uploadAction, beforeUpload, onUploadSuccess, onPreview, onTranscode, onDelete }
  }
}
</script>
