<template>
  <div class="dashboard" style="padding:16px">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card>在线设备<br/><strong>{{metrics.online}}</strong></el-card>
      </el-col>
      <el-col :span="6">
        <el-card>离线设备<br/><strong>{{metrics.offline}}</strong></el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top:16px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h3 style="margin:0">播放统计 — 设备</h3>
        <el-input v-model="deviceFilter" placeholder="筛选设备号" clearable size="small" style="width:220px"/>
      </div>
      <el-table :data="filteredDevices" style="width:100%;margin-top:12px" v-loading="loadingDevices" :row-key="row=>row.device_id">
        <el-table-column prop="device_id" label="设备号" width="220"/>
        <el-table-column prop="plays" label="播放量" width="120"/>
        <el-table-column label="平均完播率" width="140">
          <template #default="{ row }">
            <span v-if="row.avg_completion_rate!=null">{{ (row.avg_completion_rate*100).toFixed(1) }}%</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="详细信息" width="120">
          <template #default="{ row }">
            <el-button type="text" size="small" @click="openDeviceDetail(row.device_id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card style="margin-top:16px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h3 style="margin:0">播放统计 — 广告</h3>
        <el-input v-model="adFilter" placeholder="筛选素材名" clearable size="small" style="width:220px"/>
      </div>
      <el-table :data="filteredAds" style="width:100%;margin-top:12px" v-loading="loadingAds" :row-key="row=>row.ad_file_name">
        <el-table-column prop="ad_file_name" label="素材名"/>
        <el-table-column label="广告商" width="180">
          <template #default="{ row }">{{ row.advertiser || '-' }}</template>
        </el-table-column>
        <el-table-column prop="plays" label="播放量" width="120"/>
        <el-table-column label="平均完播率" width="140">
          <template #default="{ row }">
            <span v-if="row.avg_completion_rate!=null">{{ (row.avg_completion_rate*100).toFixed(1) }}%</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="待支付广告费(元)" width="160">
          <template #default="{ row }">
            <span v-if="row.estimated_cost!=null">{{ formatMoney(row.estimated_cost) }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="详细信息" width="120">
          <template #default="{ row }">
            <el-button type="text" size="small" @click="openAdDetail(row.ad_file_name)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

        <!-- 设备详情弹窗 -->
        <el-dialog v-model="deviceDetailVisible" :title="deviceDetailTitle" width="800px">
          <div style="margin-bottom:8px"><strong>设备：</strong>{{ deviceDetail && deviceDetail.device_id ? deviceDetail.device_id : '-' }}</div>
      <el-table :data="(deviceDetail && deviceDetail.items) || []" style="width:100%" empty-text="暂无数据">
        <el-table-column label="开始时间" width="180">
          <template #default="{ row }">{{ formatTs(row.start_time) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="180">
          <template #default="{ row }">{{ formatTs(row.end_time) }}</template>
        </el-table-column>
        <el-table-column prop="ad_file_name" label="素材名"/>
        <el-table-column label="时长(s)" width="120">
          <template #default="{ row }">{{ row.duration_ms!=null ? (Number(row.duration_ms)/1000).toFixed(1) : '-' }}</template>
        </el-table-column>
        <el-table-column label="是否有效" width="100">
           <template #default="{ row }">{{ formatIsValid(row) }}</template>
        </el-table-column>
        <el-table-column label="完播率" width="120">
          <template #default="{ row }">{{ row.completion_rate!=null ? (row.completion_rate*100).toFixed(1) + '%' : '-' }}</template>
        </el-table-column>
        <el-table-column prop="play_result" label="判定" width="120"/>
      </el-table>
    </el-dialog>  

    <!-- 素材详情弹窗 -->
      <el-dialog v-model="adDetailVisible" :title="adDetailTitle" width="800px">
      <div style="margin-bottom:8px">
        <strong>素材：</strong>{{ adDetail && adDetail.ad_file_name ? adDetail.ad_file_name : '-' }}
        <span style="margin-left:16px"><strong>广告主：</strong>{{ (adDetail && (adDetail.advertiser || (adDetail.items && adDetail.items[0] && adDetail.items[0].advertiser))) ? (adDetail.advertiser || (adDetail.items && adDetail.items[0] && adDetail.items[0].advertiser)) : '-' }}</span>
      </div>
      <div v-if="adDetail">
        <el-table :data="(adDetail && adDetail.items) || []" style="width:100%">
          <el-table-column label="开始时间" width="180">
            <template #default="{ row }">{{ formatTs(row.start_time) }}</template>
          </el-table-column>
          <el-table-column label="结束时间" width="180">
            <template #default="{ row }">{{ formatTs(row.end_time) }}</template>
          </el-table-column>
          <el-table-column prop="device_id" label="设备号" width="220"/>
          <el-table-column label="时长(s)" width="120">
            <template #default="{ row }">{{ row.duration_ms!=null ? (Number(row.duration_ms)/1000).toFixed(1) : '-' }}</template>
          </el-table-column>
          <el-table-column label="是否有效" width="100">
             <template #default="{ row }">{{ formatIsValid(row) }}</template>
          </el-table-column>
          <el-table-column label="完播率" width="120">
            <template #default="{ row }">{{ row.completion_rate!=null ? (row.completion_rate*100).toFixed(1) + '%' : '-' }}</template>
          </el-table-column>
          <el-table-column label="付费情况" width="140">
            <template #default="{ row }">
              <span>{{ formatBilling(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="play_result" label="判定" width="120"/>
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import api from '../api'
import { devicesSummary, deviceDetail, adsSummary, adDetail } from '../api/adstats'
export default {
  data(){
    return {
      metrics:{online:0,offline:0,plays:0,complete_rate:0},
      devicesSummary: [],
      adsSummary: [],
      deviceFilter: '',
      adFilter: '',
      loadingDevices: false,
      loadingAds: false,
      deviceDetailVisible: false,
      deviceDetail: null,
      adDetailVisible: false,
      adDetail: null
    }
  },
  computed: {
    filteredDevices(){
      const f = this.deviceFilter && String(this.deviceFilter).trim().toLowerCase()
      if(!f) return this.devicesSummary
      return (this.devicesSummary || []).filter(r => String(r.device_id||'').toLowerCase().includes(f))
    },
    filteredAds(){
      const f = this.adFilter && String(this.adFilter).trim().toLowerCase()
      if(!f) return this.adsSummary
      return (this.adsSummary || []).filter(r => String(r.ad_file_name||'').toLowerCase().includes(f))
    },
    deviceDetailTitle(){
      return this.deviceDetail && this.deviceDetail.device_id ? `设备 ${this.deviceDetail.device_id} — 播放详情` : '设备播放详情'
    },
    adDetailTitle(){
      return this.adDetail && this.adDetail.ad_file_name ? `素材 ${this.adDetail.ad_file_name} — 播放详情` : '素材播放详情'
    }
  },
  async mounted(){
    try{
      const r = await api.get('/analytics/summary')
      this.metrics = r.data || this.metrics
    }catch(e){ console.warn('fetch metrics failed', e) }

    this.fetchDevicesSummary()
    this.fetchAdsSummary()
  },
  methods: {
    async fetchDevicesSummary(){
      this.loadingDevices = true
      try{
        const r = await devicesSummary()
        const data = r.data || { items: [] }
        this.devicesSummary = data.items || []
      }catch(e){ console.warn('devices summary failed', e); this.devicesSummary=[] }
      finally{ this.loadingDevices = false }
    },
    async openDeviceDetail(device_id){
      console.log('>>> openDeviceDetail START <<<', device_id)
      try{
        console.debug('openDeviceDetail clicked', device_id)
        // show dialog immediately for responsiveness
        this.deviceDetail = { device_id: device_id, items: [] }
        this.deviceDetailVisible = true
        const r = await deviceDetail(device_id)
        console.debug('deviceDetail response', r)
        this.deviceDetail = (r && r.data) ? r.data : (r || { items: [] })
        console.log('deviceDetail after assign:', this.deviceDetail)
        console.log('items:', this.deviceDetail.items)
      }catch(e){ console.warn('device detail failed', e) }
    },
    async fetchAdsSummary(){
      this.loadingAds = true
      try{
        const r = await adsSummary()
        const data = r.data || { items: [] }
        this.adsSummary = (data.items || []).map(it => ({ ...it, estimated_cost: null }))

        // for each ad, fetch detail and compute total valid play duration
        const promises = this.adsSummary.map(async row => {
          try{
            const dr = await adDetail(row.ad_file_name)
            const ddata = (dr && dr.data) ? dr.data : (dr || { items: [] })
            const items = ddata.items || []
            const totalMs = items.reduce((s, it) => {
              if(!it) return s
              const audit = it.audit_result || {}
              const isValid = (it.is_valid === true || it.is_valid === 'true') || (audit.is_valid === true || audit.is_valid === 'true')
              const dur = (it.duration_ms != null) ? Number(it.duration_ms) : (audit.duration_ms != null ? Number(audit.duration_ms) : null)
              // Only count when is_valid is true AND billing_status is unbilled
              let bs = (it.billing_status || audit.billing_status || '')
              bs = (bs == null) ? '' : String(bs).trim().toLowerCase()
              if(isValid && bs === 'unbilled' && dur != null) return s + dur
              return s
            }, 0)
            // 10 元每秒
            row.estimated_cost = (Number(totalMs) / 1000) * 10
          }catch(e){
            console.warn('compute estimated cost failed for', row.ad_file_name, e)
            row.estimated_cost = null
          }
        })
        await Promise.all(promises)
      }catch(e){ console.warn('ads summary failed', e); this.adsSummary=[] }
      finally{ this.loadingAds = false }
    },
    async openAdDetail(ad_file_name){
      try{
        console.debug('openAdDetail clicked', ad_file_name)
        this.adDetail = { ad_file_name: ad_file_name, items: [] }
        this.adDetailVisible = true
        const r = await adDetail(ad_file_name)
        console.debug('adDetail response', r)
        this.adDetail = (r && r.data) ? r.data : (r || { items: [] })
      }catch(e){ console.warn('ad detail failed', e) }
    }
    ,
    formatTs(v){
      if(!v && v !== 0) return '-'
      try{
        // if numeric (ms or s), normalize
        if(typeof v === 'number'){
          // if it's seconds (10-digit), convert to ms
          if(v < 1e12) v = v * 1000
          const d = new Date(v)
          return d.toLocaleString()
        }
        // if string, try parse
        const d = new Date(v)
        if(isNaN(d.getTime())) return String(v)
        return d.toLocaleString()
      }catch(e){ return String(v) }
    }
    ,
    formatMoney(v){
      if(v == null || isNaN(Number(v))) return '-'
      return Number(v).toFixed(2)
    },
    formatBilling(row){
      try{
        if(!row) return '-'
        const audit = row.audit_result || {}
        const isValid = (row.is_valid === true || row.is_valid === 'true') || (audit.is_valid === true || audit.is_valid === 'true')
        const isInvalid = (row.is_valid === false || row.is_valid === 'false') || (audit.is_valid === false || audit.is_valid === 'false')
        if(isInvalid) return '无需付费'
        if(isValid){
          let bs = (row.billing_status || audit.billing_status || '')
          console.log('formatBilling billing_status', bs)
          bs = (bs == null) ? '' : String(bs).trim().toLowerCase()
          if(bs === 'pending') return '需要人工复核'
          if(bs === 'unbilled') return '待支付'
          if(bs === 'billed') return '已计费'
          if(bs === 'ignored') return '无需付费'
          if(bs) return bs
          // missing billing_status: log full row for backend debugging and show fallback
          console.warn('formatBilling missing billing_status for row:', row)
          return '待确认'
        }
        return '-'
      }catch(e){ return '-' }
    },
    formatIsValid(row){
      try{
        if(!row) return '-'
        const audit = row.audit_result || {}
        if(row.is_valid === false || row.is_valid === 'false' || audit.is_valid === false || audit.is_valid === 'false') return '否'
        if(row.is_valid === true || row.is_valid === 'true' || audit.is_valid === true || audit.is_valid === 'true') return '是'
        return '-'
      }catch(e){ return '-' }
    }
  }
}
</script>

