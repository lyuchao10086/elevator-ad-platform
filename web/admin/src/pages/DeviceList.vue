<template>
  <div class="master-map-container">
    <div class="left-panel">
      <el-collapse v-model="filterCollapsed" accordion>
        <el-collapse-item title="筛选" name="1">
          <div class="filter-row">
            <el-input v-model="filters.q" placeholder="设备ID或名称" clearable @clear="fetch" @keyup.enter.native="onFilterApply" size="small" />
            <el-select v-model="filters.city" placeholder="城市" clearable size="small" style="width:120px;margin-left:8px" @change="onFilterApply">
              <el-option v-for="c in cityOptions" :key="c" :label="c" :value="c" />
            </el-select>
            <el-select v-model="filters.status" placeholder="状态" clearable size="small" style="width:120px;margin-left:8px" @change="onFilterApply">
              <el-option label="online" value="online" />
              <el-option label="offline" value="offline" />
              <el-option label="unknown" value="unknown" />
            </el-select>
          </div>
        </el-collapse-item>
      </el-collapse>

      <div class="device-list">
        <div v-if="devices.length===0" class="empty">暂无设备数据</div>
        <div v-for="d in devices" :key="d.device_id" class="device-item">
          <div class="device-card" :data-id="d.device_id"
               :class="{ selected: selectedId===d.device_id, hovered: hoveredId===d.device_id }"
               @mouseenter="onCardHover(d.device_id)" @mouseleave="onCardLeave(d.device_id)"
               @click="onCardClick(d)">
            <div class="card-left">
              <div class="status-dot" :class="d.status"></div>
            </div>
            <div class="card-main">
              <div class="title">{{ d.name || d.device_id }}</div>
              <div class="meta">ID: {{ d.device_id }} · {{ d.city || '-' }}</div>
            </div>
            <div class="card-right">
              <div class="coord">{{ formatCoord(d.lat, d.lon) }}</div>
              <el-button type="text" size="small" @click.stop="toggleDetail(d)">{{ expandedId===d.device_id ? '收起' : '详情' }}</el-button>
            </div>
          </div>
          <!-- inline detail panel -->
          <div v-if="expandedId===d.device_id" class="device-detail">
            <div class="detail-grid">
              <div><strong>设备ID</strong></div><div>{{ d.device_id }}</div>
              <div><strong>名称</strong></div><div>{{ d.name || '-' }}</div>
              <div><strong>状态</strong></div><div>{{ d.status || '-' }}</div>
              <div><strong>经纬度</strong></div><div>{{ formatCoord(d.lat, d.lon) }}</div>
              <div><strong>固件</strong></div><div>{{ d.firmware_version || '-' }}</div>
              <div><strong>城市</strong></div><div>{{ d.city || '-' }}</div>
            </div>
            <div class="detail-actions">
              <el-button size="small" type="primary" @click="focusOnDevice(d)">定位</el-button>
              <el-button size="small" @click="quickCommand(d)">下发指令</el-button>
              <el-button size="small" @click="expandedId = null">关闭</el-button>
            </div>
          </div>
        </div>
      </div>

      <div class="left-bottom">
        <div class="stats">共 {{ total }} 台设备</div>
        <el-pagination background layout="prev, pager, next" :total="total" :page-size="pageSize" @current-change="onPage"/>
      </div>
    </div>

    <div class="map-panel">
      <div id="device-map" class="map-root"></div>
      <div class="map-controls">
        <el-button size="small" type="primary" @click="resetMapView" title="复位地图到中国全域">复位</el-button>
      </div>
    </div>
  </div>
</template>



<script>
import api from '../api'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const BRAND_COLOR = '#2f8cff'

export default {
  data(){
    return {
      devices: [],
      filters: { q: '', city: '', status: '' },
      cityOptions: [],
      page: 1,
      pageSize: 20,
      total: 0,
      map: null,
      markersMap: {},
      selectedId: null,
      hoveredId: null,
      expandedId: null,
      filterCollapsed: ['1']
    }
  },
  methods: {
    async fetch(){
      const params = { q: this.filters.q || undefined, page: this.page, page_size: this.pageSize }
      try{
        const r = await api.get('/devices/', { params })
        if(r.data?.error){
          this.$message.error('设备查询错误: ' + r.data.error)
          this.devices = []
          this.total = 0
          return
        }
        // apply simple client-side filter for city/status if backend not support
        let items = r.data?.items || []
        if(this.filters.city){ items = items.filter(x => x.city === this.filters.city) }
        if(this.filters.status){ items = items.filter(x => x.status === this.filters.status) }
        this.devices = items
        this.total = r.data?.total || items.length
        this.cityOptions = Array.from(new Set((r.data?.items || []).map(i => i.city).filter(Boolean))).slice(0,50)
        this.updateMarkers()
      }catch(e){
        this.$message.error('请求失败')
        console.error(e)
      }
    },
    onFilterApply(){ this.page = 1; this.fetch() },
    onPage(p){ this.page = p; this.fetch() },
    formatCoord(lat, lon){ if(!lat && !lon) return '-'; return `${(lat||'')}, ${(lon||'')}` },
    openDetail(row){ this.$router.push(`/devices/${row.device_id}`) },
    toggleDetail(d){
      if(this.expandedId === d.device_id) this.expandedId = null
      else this.expandedId = d.device_id
    },
    quickCommand(row){
      this.$router.push({ path: '/commands', query: { target_device_id: row.device_id } })
    },
    onCardHover(id){ this.hoveredId = id; this.highlightMarker(id, true) },
    onCardLeave(id){ if(this.hoveredId===id) this.hoveredId = null; this.highlightMarker(id, false) },
    onCardClick(d){ this.selectedId = d.device_id; this.focusOnDevice(d); },
    initMap(){
      if(this.map) return
      this.map = L.map('device-map', { center:[30.6,114.3], zoom:5, preferCanvas:true })
      const tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
      })
      tiles.addTo(this.map)
      // apply weak basemap style via CSS filter on tile pane
      const tilePane = document.querySelector('#device-map .leaflet-tile-pane')
      if(tilePane) tilePane.style.filter = 'grayscale(60%) contrast(90%) brightness(95%)'
    },
    resetMapView(){
      if(!this.map) this.initMap()
      try{
        // center and zoom to show mainland China nicely
        this.map.setView([35.0, 103.0], 4)
      }catch(e){ console.warn('resetMapView failed', e) }
    },
    updateMarkers(){
      if(!this.map) this.initMap()
      // remove old markers
      Object.values(this.markersMap).forEach(m => { try{ this.map.removeLayer(m) }catch(e){} })
      this.markersMap = {}
      const bounds = []
      for(const d of this.devices){
        const lat = parseFloat(d.lat)
        const lon = parseFloat(d.lon)
        if(!Number.isFinite(lat) || !Number.isFinite(lon)) continue
        const marker = L.circleMarker([lat, lon], {
          radius: 7,
          color: '#ffffff',
          weight: 1,
          fillColor: BRAND_COLOR,
          fillOpacity: 1
        })
        marker.addTo(this.map)
        marker.on('mouseover', () => { this.hoveredId = d.device_id; this.scrollCardIntoView(d.device_id); this.setMarkerHoverStyle(d.device_id, true) })
        marker.on('mouseout', () => { if(this.hoveredId===d.device_id) this.hoveredId = null; this.setMarkerHoverStyle(d.device_id, false) })
        marker.on('click', () => { this.selectedId = d.device_id; this.focusOnDevice(d) })
        this.markersMap[d.device_id] = marker
        bounds.push([lat, lon])
      }
      if(bounds.length===1){ this.map.setView(bounds[0], 12) }
      else if(bounds.length>1){ this.map.fitBounds(bounds, { padding:[60,60] }) }
    },
    highlightMarker(id, hover){
      const m = this.markersMap[id]
      if(!m) return
      if(hover){ m.setStyle({ radius: 10, weight:2, color:'#fff' }) }
      else { m.setStyle({ radius:7, weight:1, color:'#fff' }) }
    },
    setMarkerHoverStyle(id, hover){ this.highlightMarker(id, hover) },
    focusOnDevice(d){ const lat=parseFloat(d.lat), lon=parseFloat(d.lon); if(Number.isFinite(lat)&&Number.isFinite(lon)){ this.map.flyTo([lat,lon], 12, {duration:0.6}) } },
    scrollCardIntoView(id){ // ensure card is visible in left panel
      this.$nextTick(()=>{
        const el = this.$el.querySelector(`.device-card[data-id="${id}"]`)
        if(el && el.scrollIntoView) el.scrollIntoView({ block:'center', behavior:'smooth' })
      })
    }
  },
  mounted(){ this.initMap(); this.fetch() }
}
</script>

<style scoped>
.master-map-container{ display:flex; height:calc(100vh - 40px); gap:16px; padding:12px }
.left-panel{ flex-basis:35%; background:#ffffff; border-radius:8px; padding:12px; box-shadow:0 1px 2px rgba(0,0,0,0.04); display:flex; flex-direction:column }
.map-panel{ flex:1; border-radius:8px; overflow:hidden }
.map-root{ width:100%; height:100%; }
.filter-row{ display:flex; gap:8px; align-items:center }
.device-list{ margin-top:12px; overflow:auto; flex:1 }
.device-card{ display:flex; align-items:center; padding:10px; border-radius:6px; margin-bottom:8px; cursor:pointer; background:#fff; transition:box-shadow .15s, transform .08s }
.device-card:hover{ box-shadow:0 6px 18px rgba(47,140,255,0.08); transform:translateY(-2px) }
.device-card.selected{ box-shadow:0 10px 30px rgba(47,140,255,0.12); border:1px solid rgba(47,140,255,0.12) }
.card-left{ width:36px; display:flex; align-items:center; justify-content:center }
.status-dot{ width:12px; height:12px; border-radius:50%; border:2px solid rgba(255,255,255,0.5) }
.status-dot.online{ background:#2f8cff }
.status-dot.offline{ background:#d9d9d9 }
.status-dot.unknown{ background:#bfbfbf }
.card-main{ flex:1; padding-left:8px }
.title{ font-weight:600; color:#24324a }
.meta{ color:#8b98a8; font-size:12px; margin-top:4px }
.card-right{ display:flex; flex-direction:column; align-items:flex-end; gap:6px }
.coord{ font-size:12px; color:#9aa6b6 }
.left-bottom{ margin-top:8px; display:flex; align-items:center; justify-content:space-between }
.empty{ color:#9aa6b6; padding:24px; text-align:center }

.device-detail{ background: #fbfdff; border-left: 3px solid rgba(47,140,255,0.12); padding:12px 14px; margin-bottom:10px; border-radius:6px }
.detail-grid{ display:grid; grid-template-columns: 120px 1fr; gap:8px 12px; color:#4b5966; font-size:13px }
.detail-actions{ margin-top:10px; display:flex; gap:8px; justify-content:flex-end }

/* reduce visual weight of map base tiles */
#device-map .leaflet-tile-pane{ filter: grayscale(60%) contrast(90%) brightness(95%) }

.map-panel{ position: relative }
.map-controls{ position: absolute; top: 12px; right: 12px; z-index: 400 }


</style>
