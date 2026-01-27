<template>
  <div>
    <el-input v-model="q" placeholder="搜索设备ID或名称" @keyup.enter="fetch" style="width:300px;margin-bottom:12px"/>
    <el-table :data="devices" style="width:100%">
      <el-table-column prop="device_id" label="设备ID" width="220"/>
      <el-table-column prop="name" label="名称"/>
      <el-table-column prop="status" label="状态" width="120"/>
      <el-table-column prop="firmware_version" label="固件版本" width="140"/>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button type="primary" size="small" @click="openDetail(row)">详情</el-button>
          <el-button type="warning" size="small" style="margin-left:8px" @click="quickCommand(row)">下发指令</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination background layout="prev, pager, next" :total="total" :page-size="pageSize" @current-change="onPage"/>
  </div>
</template>

<script>
import api from '../api'
export default {
  data(){return {devices:[],q:'',page:1,pageSize:20,total:0}},
  methods:{
    async fetch(){
      const params = { q:this.q, page:this.page, page_size:this.pageSize }
      const r = await api.get('/devices', { params })
      this.devices = r.data?.items || []
      this.total = r.data?.total || 0
    },
    onPage(p){ this.page = p; this.fetch() },
    openDetail(row){ this.$router.push(`/devices/${row.device_id}`) },
    quickCommand(row){
      // navigate to commands page and pass device id as query to prefill
      this.$router.push({ path: '/commands', query: { target_device_id: row.device_id } })
    }
  },
  mounted(){ this.fetch() }
}
</script>
