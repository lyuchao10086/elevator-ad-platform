<template>
  <div style="padding:16px">
    <el-row justify="space-between" align="middle" style="margin-bottom:12px">
      <el-col><h3>播放日志</h3></el-col>
      <el-col>
        <el-input v-model="deviceQuery" placeholder="设备ID" clearable size="small" style="width:220px; margin-right:8px" />
        <el-input v-model="fileQuery" placeholder="广告文件名" clearable size="small" style="width:240px; margin-right:8px" />
        <el-button type="primary" size="small" @click="fetch(1)">搜索</el-button>
        <el-button type="text" size="small" @click="fetch(page)">刷新</el-button>
      </el-col>
    </el-row>

    <el-card>
      <el-table :data="logs" style="width:100%" v-loading="loading" :row-key="row=>row.log_id">
        <el-table-column prop="log_id" label="日志ID" width="260"/>
        <el-table-column prop="device_id" label="设备号" width="180"/>
        <el-table-column prop="ad_file_name" label="素材名"/>
        <el-table-column prop="start_time" label="开始时间" width="180">
          <template #default="{ row }">{{ formatTs(row.start_time) }}</template>
        </el-table-column>
        <el-table-column prop="end_time" label="结束时间" width="180">
          <template #default="{ row }">{{ formatTs(row.end_time) }}</template>
        </el-table-column>
        <el-table-column label="时长(s)" width="120">
          <template #default="{ row }">
            <span v-if="row.duration_ms!=null">{{ (Number(row.duration_ms)/1000).toFixed(1) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="完播率" width="120">
          <template #default="{ row }">
            <span v-if="row.completion_rate!=null">{{ (row.completion_rate*100).toFixed(1) }}%</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="play_result" label="是否完播" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.play_result" type="info">{{ row.play_result }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <!-- <el-table-column prop="status_code" label="状态码" width="100"/> -->
        <!-- <el-table-column prop="is_valid" label="校验" width="100">
          <template #default="{ row }">{{ row.is_valid ? '是' : '否' }}</template>
        </el-table-column> -->
        <!-- <el-table-column prop="billing_status" label="计费状态" width="120"/> -->
        <!-- <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatCreatedAt(row.created_at) }}</template>
        </el-table-column> -->
        <!-- <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button type="text" size="small" @click="showDetail(row)">详情</el-button>
          </template>
        </el-table-column> -->
      </el-table>

      <div style="margin-top:12px;display:flex;justify-content:flex-end;align-items:center">
        <el-pagination
          background
          :current-page="page"
          :page-size="pageSize"
          layout="prev, pager, next, jumper, ->, total"
          :total="total"
          @current-change="fetch"
        />
      </div>
    </el-card>

    <el-dialog v-model:visible="detailVisible" title="日志详情" width="800px">
      <div v-if="detailRow">
        <pre style="background:#fafbff;padding:8px;border-radius:4px;max-height:420px;overflow:auto">{{ JSON.stringify(detailRow, null, 2) }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import adlogsApi from '../api/adlogs'

export default {
  setup(){
    const logs = ref([])
    const loading = ref(false)
    const page = ref(1)
    const pageSize = ref(20)
    const total = ref(0)
    const deviceQuery = ref('')
    const fileQuery = ref('')

    const detailVisible = ref(false)
    const detailRow = ref(null)

    function formatTs(s){ if(!s) return ''; try{ const d=new Date(s); return isNaN(d)? String(s) : d.toLocaleString() }catch(e){ return s } }
    function formatCreatedAt(v){ if(!v) return ''; try{ const d=new Date(Number(v)); return isNaN(d)? v : d.toLocaleString() }catch(e){ return v } }

    async function fetch(p=1){
      page.value = p
      loading.value = true
      try{
        const params = { page: page.value, page_size: pageSize.value }
        if(deviceQuery.value) params.device_id = deviceQuery.value
        if(fileQuery.value) params.ad_file_name = fileQuery.value
        const r = await adlogsApi.listAdLogs(params)
        const data = r.data || r || {}
        logs.value = data.items || data || []
        total.value = data.total || (Array.isArray(logs.value)? logs.value.length: 0)
      }catch(e){ console.warn('fetch ad logs failed', e); logs.value = []; total.value = 0 }
      finally{ loading.value = false }
    }

    async function showDetail(row){
      try{
        const r = await adlogsApi.getAdLog(row.log_id).catch(()=>null)
        detailRow.value = r?.data || row
      }catch(e){ detailRow.value = row }
      detailVisible.value = true
    }

    onMounted(()=> fetch(1))
    return { logs, loading, page, pageSize, total, deviceQuery, fileQuery, fetch, formatTs, formatCreatedAt, detailVisible, detailRow, showDetail }
  }
}
</script>

<style scoped>
.el-table .cell{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
</style>
