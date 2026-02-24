<template>
  <div style="padding:16px">
    <el-row justify="space-between" align="middle" style="margin-bottom:12px">
      <el-col><h3>投放策略</h3></el-col>
      <el-col>
        <el-button type="primary" @click="onCreate">新建策略</el-button>
      </el-col>
    </el-row>

    <el-table :data="campaigns" style="width:100%">
      <el-table-column prop="campaign_id" label="策略号" width="220"/>
      <el-table-column prop="name" label="策略名"/>
      <el-table-column prop="creator_id" label="创建者" width="140"/>
      <el-table-column prop="status" label="状态" width="120"/>
      <el-table-column prop="start_at" label="生效时间" width="160"/>
      <el-table-column prop="end_at" label="失效时间" width="160"/>
      <el-table-column prop="created_at" label="创建时间" width="180"/>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button type="text" size="small" @click="onEdit(row)">编辑</el-button>
          <el-button type="text" size="small" @click="onPublish(row)">发布</el-button>
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
    const campaigns = ref([])
    const materials = ref([])
    async function fetch(){
      try{
        const r = await api.get('/v1/campaigns')
        campaigns.value = r.data?.items || []
      }catch(e){
        campaigns.value = [ { campaign_id:'C_001', name:'早高峰投放', status:'draft', start_at:'2026-01-01', end_at:'2026-12-31' } ]
      }
        // 同步加载素材列表，供新建/编辑使用
        try{
          const m = await api.get('/v1/materials')
          materials.value = m.data?.items || []
        }catch(e){
          materials.value = []
        }
    }
    function onCreate(){ alert('打开新建策略对话（未实现）') }
    function onEdit(row){ alert('打开编辑：' + row.campaign_id) }
    async function onPublish(row){
      try{ await api.post('/v1/campaigns/' + row.campaign_id + '/publish'); alert('已发布') }catch(e){ alert('发布失败') }
    }
    onMounted(fetch)
    return { campaigns, onCreate, onEdit, onPublish, materials }
  }
}
</script>
