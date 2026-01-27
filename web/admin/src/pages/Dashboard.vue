<template>
  <div class="dashboard">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card>在线设备<br/><strong>{{metrics.online}}</strong></el-card>
      </el-col>
      <el-col :span="6">
        <el-card>离线设备<br/><strong>{{metrics.offline}}</strong></el-card>
      </el-col>
      <el-col :span="6">
        <el-card>今日播放<br/><strong>{{metrics.plays}}</strong></el-card>
      </el-col>
      <el-col :span="6">
        <el-card>完播率<br/><strong>{{metrics.complete_rate}}%</strong></el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import api from '../api'
export default {
  data(){return {metrics:{online:0,offline:0,plays:0,complete_rate:0}} },
  async mounted(){
    try{
      const r = await api.get('/analytics/summary')
      this.metrics = r.data || this.metrics
    }catch(e){
      console.warn('fetch metrics failed', e)
    }
  }
}
</script>
