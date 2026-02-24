<template>
  <div class="commands-page" style="padding:16px">
    <el-card>
      <div class="header-row" style="display:flex;align-items:center;justify-content:space-between">
        <h3 style="margin:0">指令下发</h3>
      </div>

      <div class="core" style="display:flex;gap:16px;margin-top:16px">
        <!-- 设备选择列 -->
        <div class="col devices" style="width:36%;background:#fff;padding:12px;border-radius:6px">
          <div style="display:flex;gap:8px;margin-bottom:8px">
            <el-input v-model="deviceQuery" placeholder="搜索设备ID/名称" clearable size="small" @input="onDeviceQueryChange" @keyup.enter.native="fetchDevices"/>
            <el-select v-model="filterStatus" placeholder="状态" clearable size="small" style="width:110px" @change="fetchDevices">
              <el-option label="online" value="online"/>
              <el-option label="offline" value="offline"/>
              <el-option label="unknown" value="unknown"/>
            </el-select>
          </div>

          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <div>已选：<strong>{{selectedDevices.length}}</strong> 台</div>
            <div>
              <el-button type="text" size="small" @click="selectAllVisible">全选可见</el-button>
              <el-button type="text" size="small" @click="clearSelection">清空</el-button>
            </div>
          </div>

          <div class="device-scroll" style="max-height:420px;overflow:auto;border-radius:4px;padding:6px;background:#fbfdff" v-loading="deviceLoading">
            <el-checkbox-group v-model="selectedDevices">
              <div v-for="d in devices" :key="d.device_id" class="device-row" style="display:flex;align-items:center;justify-content:space-between;padding:8px;border-radius:6px;margin-bottom:6px;background:#fff;border:1px solid #f0f3f8">
                <div style="display:flex;gap:10px;align-items:center">
                  <el-checkbox :label="d.device_id"></el-checkbox>
                  <div style="display:flex;flex-direction:column">
                    <div style="font-weight:600">{{ d.name || d.device_id }}</div>
                    <div style="font-size:12px;color:#8b98a8">{{ d.city || '-' }} · ID: {{ d.device_id }}</div>
                  </div>
                </div>
                <div style="text-align:right">
                  <el-tag :type="statusTagType(d.status)">{{ d.status || 'unknown' }}</el-tag>
                  <div style="font-size:12px;color:#9aa6b6;margin-top:4px">{{ formatCoord(d.lat,d.lon) }}</div>
                </div>
              </div>
            </el-checkbox-group>
            <div v-if="!deviceLoading && devices.length===0" style="padding:16px;color:#9aa6b6">暂无设备</div>
          </div>

          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
            <div>共 {{ totalDevices }} 台</div>
            <el-pagination background layout="prev, pager, next" :total="totalDevices" :page-size="pageSize" @current-change="onDevicePage"/>
          </div>
        </div>

        <!-- 动作选择列 -->
        <div class="col actions" style="width:28%;background:#fff;padding:12px;border-radius:6px">
          <div style="font-weight:600;margin-bottom:8px">指令</div>
          <div style="display:flex;flex-direction:column;gap:8px">
            <div v-for="act in actions" :key="act.key" :class="['ability-card', {selected: selectedAction===act.key}]" @click="selectAction(act)" style="padding:12px;border-radius:8px;border:1px solid #f3f6fa;cursor:pointer;display:flex;justify-content:space-between;align-items:flex-start">
              <div style="flex:1">
                <div style="display:flex;gap:8px;align-items:center">
                  <div style="font-weight:700">{{ act.title }}</div>
                  <el-tag size="small" v-if="act.risk" :type="act.risk==='high'? 'danger': act.risk==='medium'? 'warning' : 'success'">{{ act.risk }}</el-tag>
                </div>
                <div style="color:#7b8793;font-size:12px;margin-top:6px">{{ act.description }}</div>
                <div style="font-size:12px;color:#9aa6b6;margin-top:6px">适用设备: {{ (act.applicable || ['所有']).join(', ') }}</div>
              </div>
              <div style="margin-left:8px;text-align:right">
                
              </div>
            </div>
          </div>
        </div> 

        <!-- 详细信息 & 发送列 -->
        <!-- 详细信息 & 发送列 -->
        <div class="col params" style="flex:1;background:#fff;padding:12px;border-radius:6px;display:flex;flex-direction:column;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div style="font-weight:600;">详细信息</div>
            <div style="color:#9aa6b6;font-size:13px;">当前指令：<strong>{{ actionTitle }}</strong></div>
          </div>

          <div style="margin-top:8px;flex:1;display:flex;flex-direction:column;gap:12px;">
            <div style="flex:1;overflow:auto;">
              <!-- Dynamic detail panels by instruction -->
              <div v-if="selectedAction==='reboot'" style="padding:12px;color:#6b7786;">
                此指令将使目标设备立即重启，请确保当前设备不在关键播放期。
              </div>

              <div v-else-if="selectedAction==='set_volume'" style="padding:12px;">
                <el-form :model="params" label-width="120px">
                  <el-form-item label="目标音量" prop="volume">
                    <el-slider v-model="params.volume" :min="0" :max="100" show-input />
                  </el-form-item>
                  <el-form-item label="是否静音">
                    <el-switch v-model="params.mute" active-text="是" inactive-text="否" />
                  </el-form-item>
                </el-form>
              </div>

              <div v-else-if="selectedAction==='capture'" style="padding:12px;">
                <div style="font-size:13px;color:#7b8793;">截屏结果</div>
                <div style="margin-top:8px;border:1px dashed #e6eefc;height:220px;display:flex;align-items:center;justify-content:center;color:#9aa6b6;">
                  截屏（返回图片）
                </div>
              </div>

              <div v-else-if="selectedAction==='insert_play'" style="padding:12px;">
                <div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;">
                  <el-input v-model="materialQuery" placeholder="查询" clearable size="small" @input="onMaterialQueryChange" />
                  <el-button type="text" @click="fetchMaterials">刷新</el-button>
                </div>
                <div style="max-height:300px;overflow:auto">
                  <div v-if="materialLoading" style="padding:12px;color:#9aa6b6;">加载中...</div>
                  <div v-else>
                    <div
                      v-for="m in materialsFiltered"
                      :key="m.material_id"
                      @click="selectMaterial(m)"
                      :style="materialItemStyle(m)"
                      class="material-item"
                      style="padding:8px;border-radius:6px;display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;cursor:pointer;"
                    >
                      <div>
                        <div style="font-weight:600;">{{ m.file_name || m.material_id }}</div>
                        <div style="font-size:12px;color:#8b98a8;">
                          {{ m.advertiser || m.ad_id || (m.extra && m.extra.raw && (m.extra.raw.advertiser || m.extra.raw.ad_id)) || '-' }} · {{ formatSize(m.size_bytes) }}
                        </div>
                      </div>
                      <div style="text-align:right;">
                        <el-button type="text" size="small" @click.stop="onPreviewMaterial(m)">预览</el-button>
                      </div>
                    </div>
                    <div v-if="materialsFiltered.length===0" style="color:#9aa6b6;padding:12px;">未找到素材</div>
                  </div>
                </div>
              </div>

              <div v-else style="color:#9aa6b6;padding:12px;">请选择指令以显示详细信息。</div>
            </div>

            <!-- 新增的右侧操作栏 -->
            <div style="width:280px;border-left:1px solid #f3f6fa;padding-left:12px;display:flex;flex-direction:column;gap:8px;">
              <!-- <div style="font-weight:600;margin-bottom:8px;">预览 & 说明</div>
              <div style="margin-top:6px;font-size:13px;color:#9aa6b6;">
                发送风险提示：指令可能改变设备播放/网络/重启行为，请先确认目标设备在线并备份关键状态。
              </div> -->
              <div style="margin-top:auto;display:flex;gap:8px;justify-content:flex-end;">
                <!-- <el-input-number v-model="expireSec" :min="1" :step="10" label="过期(s)" /> -->
                <el-button @click="resetParams" size="small">重置</el-button>
                <el-button type="primary" :loading="sending" @click="onPrepareSend" size="small">确认并发送</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 确认弹窗 -->
    <el-dialog :visible.sync="confirmVisible" title="确认下发指令" width="600px">
      <div>
        <p><strong>目标设备：</strong> {{ selectedDevices.length }} 台</p>
        <p><strong>动作：</strong> {{ actionTitle }}</p>
        <p><strong>过期：</strong> {{ expireSec }} 秒</p>
        <p><strong>参数：</strong></p>
        <pre style="background:#fafbff;padding:8px;border-radius:4px;max-height:240px;overflow:auto">{{ finalPayloadPreview }}</pre>
      </div>
      <template #footer>
        <el-button @click="confirmVisible=false">取消</el-button>
        <el-button type="primary" :loading="sending" @click="onSend">确认并发送</el-button>
      </template>
    </el-dialog>

    <!-- 近期指令时间轴 -->
    <el-card style="margin-top:16px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h3 style="margin:0">近期指令（时间轴）</h3>
        <el-button type="text" @click="fetchCommands">刷新</el-button>
      </div>
      <el-timeline style="margin-top:12px">
        <el-timeline-item v-for="cmd in commands" :key="cmd.cmd_id" :timestamp="formatTs(cmd.send_ts)" :placement="'top'">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <div style="font-weight:600">{{ cmd.action }} · {{ cmd.target_device_id || cmd.device_group_id || '多设备' }}</div>
              <div style="font-size:13px;color:#7b8793">状态：<el-tag :type="statusTagType(cmd.status)">{{ cmd.status }}</el-tag></div>
            </div>
            <div style="width:240px;text-align:right;color:#6b7786;font-size:12px">{{ cmd.result || '' }}</div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import api from '../api'
import { sendCommand, listCommands } from '../api/commands'
import { useRoute } from 'vue-router'

function uuidv4(){
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c=>{
    const r = Math.random()*16|0, v = c=='x'? r: (r&0x3|0x8)
    return v.toString(16)
  })
}

// 简单的动作模板定义，可按需扩展或从后端加载
const ACTION_TEMPLATES = [
  { key: 'reboot', title: '重启', description: '立即重启设备', fields: [] },
  { key: 'set_volume', title: '设置音量', description: '调整设备音量（0-100）', fields: [ { key:'volume', label:'音量', hint:'0-100', type:'number', props:{min:0,max:100} } ] },
  { key: 'capture', title: '截屏', description: '让设备截取当前屏幕并上传', fields: [ { key:'save_to', label:'保存位置', hint:'例如: /screenshots/1.jpg', type:'text' } ] },
  { key: 'insert_play', title: '视频插播', description: '临时插播一段视频素材', fields: [ { key:'material_id', label:'素材ID', hint:'选择已上传的视频素材', type:'text' }, { key:'priority', label:'优先级', hint:'0-9，越大优先级越高', type:'number', props:{min:0,max:9} } ] }
]

export default {
  setup(){
    const route = useRoute()
    const activeStep = ref(0)

    // devices
    const devices = ref([])
    const deviceQuery = ref('')
    const filterStatus = ref('')
    const page = ref(1)
    const pageSize = ref(50)
    const totalDevices = ref(0)
    const selectedDevices = ref([])
    const deviceLoading = ref(false)
    let queryTimer = null

    // actions
    const actions = ACTION_TEMPLATES
    const selectedAction = ref('')

    // params
    const paramTemplate = computed(()=> actions.find(a=>a.key===selectedAction.value) || null)
    const params = reactive({})
    const expireSec = ref(60)

    // confirmation & sending
    const confirmVisible = ref(false)
    const sending = ref(false)

    // recent commands
    const commands = ref([])
    // materials for insert_play
    const materials = ref([])
    const materialQuery = ref('')
    const materialLoading = ref(false)
    let materialTimer = null

    async function fetchMaterials(){
      materialLoading.value = true
      try{
        console.debug('fetchMaterials: requesting /v1/materials', { q: materialQuery.value })
        const r = await api.get('/v1/materials', { params: { q: materialQuery.value || undefined, page: 1, page_size: 200 } })
        console.debug('fetchMaterials: response', r && r.data)
        materials.value = r.data?.items || r.data || []
        console.debug('fetchMaterials: materials set, count=', materials.value && materials.value.length)
      }catch(e){
        console.warn('fetch materials failed', e)
        // fallback mock (same as Materials.vue) to ensure UI remains usable in dev
        materials.value = [
          { material_id: 'M_001', advertiser: 'adv_101', file_name: 'nike_shoe.mp4', oss_url: 'https://oss.example.com/ads/nike_shoe.mp4', size_bytes: 20485760, status: 'ready', created_at: '2026-01-29T16:09:09Z', updated_at: '2026-01-29T16:09:09Z', tags: ['示例'] }
        ]
      }finally{ materialLoading.value = false; console.debug('fetchMaterials: materialLoading=false') }
    }

    function onMaterialQueryChange(){
      if(materialTimer) clearTimeout(materialTimer)
      materialTimer = setTimeout(()=> fetchMaterials(), 300)
    }

    const materialsFiltered = computed(()=>{
      const q = (materialQuery.value || '').toLowerCase().trim()
      if(!q) return materials.value
      return materials.value.filter(m => (m.material_id||'').toLowerCase().includes(q) || (m.file_name||'').toLowerCase().includes(q) )
    })

    function selectMaterial(m){ params.material_id = m.material_id; selectedMaterial.value = m.material_id }
    const selectedMaterial = ref(null)
    function materialItemStyle(m){ return selectedMaterial.value===m.material_id ? { boxShadow:'0 8px 24px rgba(47,140,255,0.06)', border:'1px solid rgba(47,140,255,0.12)' } : {} }
    function onPreviewMaterial(m){ window.open(m.oss_url || '#') }

    async function fetchDevices(){
      deviceLoading.value = true
      try{
        const paramsQ = { q: deviceQuery.value || undefined, page: page.value, page_size: pageSize.value }
        const r = await api.get('/v1/devices', { params: paramsQ }).catch(async ()=>{
          // fallback to older endpoint
          return api.get('/devices/', { params: paramsQ })
        })
        const data = r.data || {}
        const items = data.items || data || []
        let list = items
        if(filterStatus.value) list = list.filter(x=>x.status===filterStatus.value)
        devices.value = list
        totalDevices.value = data.total || list.length
      }catch(e){ console.warn('fetch devices failed', e); devices.value = []; totalDevices.value = 0 }
      finally{ deviceLoading.value = false }
    }

    function onDeviceQueryChange(){
      if(queryTimer) clearTimeout(queryTimer)
      queryTimer = setTimeout(()=>{ page.value = 1; fetchDevices() }, 380)
    }

    function onDevicePage(p){ page.value = p; fetchDevices() }
    function selectAllVisible(){ selectedDevices.value = devices.value.map(d=>d.device_id) }
    function clearSelection(){ selectedDevices.value = [] }
    function formatCoord(lat,lon){ if(!lat&&!lon) return '-'; return `${lat||''}, ${lon||''}` }
    function statusTagType(s){ if(!s) return 'info'; if(s==='online') return 'success'; if(s==='offline') return 'danger'; return 'warning' }

    function formatSize(n){
      if(!n && n !== 0) return ''
      const kb = 1024
      if(n < kb) return n + ' B'
      if(n < kb*kb) return (n/kb).toFixed(1) + ' KB'
      if(n < kb*kb*kb) return (n/(kb*kb)).toFixed(1) + ' MB'
      return (n/(kb*kb*kb)).toFixed(1) + ' GB'
    }

    // actions preview & selection
    const actionTitle = computed(()=> (actions.find(a=>a.key===selectedAction.value)?.title) || '-')
    const previewOnly = ref(false)

    function selectAction(act){
      if(!act) return
      console.debug('selectAction()', act && act.key)
      selectedAction.value = act.key
      // populate defaults for structured form
      if(act.fields){
        act.fields.forEach(f=> {
          if(f.default!==undefined) params[f.key] = f.default
          else if(f.type==='number') params[f.key] = f.props && f.props.min!==undefined ? f.props.min : 0
          else if(f.type==='boolean') params[f.key] = f.default===undefined? false : f.default
          else params[f.key] = ''
        })
      }
      activeStep.value = 1
      if(act.key === 'insert_play') {
        // fetch materials when entering insert_play; ensure async handling
        fetchMaterials().catch(e=>{ console.warn('fetchMaterials failed', e) })
      }
    }

    function previewTemplate(act){
      if(!act) return
      selectAction(act)
      // fill example values
      if(act.fields){ act.fields.forEach(f=> { params[f.key] = f.props && f.props.min ? f.props.min : (f.type==='number'?0:'example') }) }
      activeStep.value = 2
    }

    function fieldComponent(type){ if(type==='number') return 'el-input-number'; if(type==='boolean') return 'el-switch'; return 'el-input' }

    function resetParams(){
      // clear structured params
      Object.keys(params).forEach(k=> delete params[k])
      // clear selected devices and action
      selectedDevices.value = []
      selectedAction.value = ''
      // clear material selection and queries
      selectedMaterial.value = null
      materialQuery.value = ''
      // reset misc
      expireSec.value = 60
      previewOnly.value = false
      activeStep.value = 0
    }

    function fieldRule(f){
      const rules = []
      if(f.required) rules.push({ required:true, message:`${f.label} 为必填`, trigger:'change' })
      if(f.type==='number' && f.props){ if(f.props.min!==undefined) rules.push({ validator:(rule, value, cb)=> { if(value< f.props.min) cb(new Error(`${f.label} >= ${f.props.min}`)); else cb() }, trigger:'change'}) }
      return rules
    }

    // prepare confirm (validate structured form)
    const paramRules = {}
    function onPrepareSend(){
      const hasDevices = selectedDevices.value && selectedDevices.value.length>0
      const hasAction = !!selectedAction.value
      if(!hasDevices && !hasAction){
        return alert('请先选择目标设备和指令')
      }
      if(!hasDevices && hasAction){
        return alert('未选择设备：请先从左侧列表选择至少一台设备')
      }
      if(hasDevices && !hasAction){
        return alert('未选择指令：请在中间栏选择一个指令')
      }
      // validate form if template exists
      const tmpl = paramTemplate.value
      if(tmpl && tmpl.fields && tmpl.fields.length){
        // basic required check for structured fields
        for(const f of tmpl.fields){
          if(f.required && (params[f.key] === '' || params[f.key] === undefined || params[f.key] === null)){
            return alert(`${f.label} 为必填`)
          }
        }
      }
      confirmVisible.value = true
    }

    const finalPayloadPreview = computed(()=>{
      const p = JSON.parse(JSON.stringify(params || {}))
      const payload = { targets: selectedDevices.value, action: selectedAction.value, params: p, expire_sec: expireSec.value }
      return JSON.stringify(payload,null,2)
    })

    const previewJSON = computed(()=>{
      try{ return JSON.stringify(params,null,2) }catch(e){ return '{}'}
    })

    async function onSend(){
      confirmVisible.value = false
      if(selectedDevices.value.length===0) return
      sending.value = true
      try{
        const payload = {
          cmd_id: uuidv4(),
          target_device_id: selectedDevices.value.length===1 ? selectedDevices.value[0] : undefined,
          device_group_id: undefined,
          target_device_ids: selectedDevices.value.length>1 ? selectedDevices.value : undefined,
          action: selectedAction.value,
          params: JSON.parse(JSON.stringify(params || {})),
          send_ts: Math.floor(Date.now()/1000),
          expire_sec: expireSec.value
        }
        const res = await sendCommand(payload)
        // optimistic feedback
        alert('指令已下发: ' + (res.data?.cmd_id || payload.cmd_id))
        await fetchCommands()
        activeStep.value = 0
      }catch(e){ console.error(e); alert('下发失败') }
      finally{ sending.value = false }
    }

    async function fetchCommands(){
      try{
        const r = await listCommands({ limit: 30 })
        commands.value = r.data?.items || r.data || []
      }catch(e){ console.warn('fetch commands failed', e) }
    }

    function formatTs(ts){ if(!ts) return ''; try{ return new Date(ts*1000).toLocaleString() }catch(e){ return ts } }

    onMounted(()=>{
      // prefill from query
      if(route.query.target_device_id){ selectedDevices.value = [route.query.target_device_id] }
      fetchDevices(); fetchCommands()
    })

    // react to route changes so opening commands while already mounted still picks target
    watch(() => route.query.target_device_id, (val) => {
      if(val){
        // support comma-separated list
        if(typeof val === 'string' && val.includes(',')){
          selectedDevices.value = val.split(',').map(s=>s.trim()).filter(Boolean)
        }else{
          selectedDevices.value = [val]
        }
      }
    })

    return {
      activeStep,
      devices, deviceQuery, filterStatus, page, pageSize, totalDevices, selectedDevices, deviceLoading,
      onDeviceQueryChange,
      fetchDevices, onDevicePage, selectAllVisible, clearSelection, formatCoord, statusTagType,
      formatSize,
      actions, selectedAction, selectAction, previewTemplate, actionTitle, paramTemplate, params, fieldComponent,
      resetParams, expireSec, onPrepareSend, confirmVisible, finalPayloadPreview, onSend, sending, previewOnly,
      materials, materialQuery, materialLoading, materialsFiltered, selectMaterial, selectedMaterial, onPreviewMaterial, fetchMaterials, onMaterialQueryChange, materialItemStyle,
      commands, previewJSON, fetchCommands
    }
  }
}
</script>

<style scoped>
.device-row:hover{ box-shadow: 0 6px 18px rgba(47,140,255,0.04); transform: translateY(-2px); }
 .ability-card.selected{ box-shadow: 0 10px 30px rgba(47,140,255,0.08); border-color: rgba(47,140,255,0.14); transform: translateY(-2px); }
</style>
