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
                  <div v-if="sending && !snapshotUrl" style="color:#7b8793">请求已发送，等待设备上传截图...</div>
                  <div v-else-if="snapshotUrl">
                    <img :src="snapshotUrl" alt="snapshot" style="max-height:100%;max-width:100%;object-fit:contain;" />
                  </div>
                  <div v-else style="color:#9aa6b6">尚未截屏或未返回图片</div>
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
    
    <!-- 指令日志表格 -->
    <el-card style="margin-top:16px">
      <div style="display:flex;align-items:center;gap:12px;justify-content:flex-start">
        <h3 style="margin:0">操作日志</h3>
        <div style="display:flex;gap:8px;align-items:center;margin-left:8px">
          <el-select v-model="logFilterDevice" placeholder="设备号" clearable size="small" style="width:220px">
            <el-option v-for="d in devices" :key="d.device_id" :label="(d.name ? d.name + ' · ' : '') + d.device_id" :value="d.device_id" />
          </el-select>
          <el-select v-model="logFilterAction" placeholder="指令" clearable size="small" style="width:140px">
            <el-option v-for="a in actions" :key="a.key" :label="a.title" :value="a.key" />
          </el-select>
          <el-button type="primary" size="small" @click="fetchCommandLogs(1)">搜索</el-button>
          <el-button type="text" size="small" @click="fetchCommandLogs(logsPage)">刷新</el-button>
        </div>
      </div>

      <div style="margin-top:12px">
      <el-table :data="commandLogs" style="width:100%" v-loading="logsLoading" :row-key="row => row.id">
          <!-- <el-table-column prop="id" label="ID" width="70" /> -->
          <el-table-column prop="cmd_id" label="指令代码" width="220" />
          <el-table-column prop="device_id" label="设备号" width="140" />
          <el-table-column prop="action" label="指令" width="120" />
          <el-table-column label="指令信息">
            <template #default="{ row }">
              <div style="max-width:360px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ formatParams(row.action, row.params) }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="状态" label="Status" width="110">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="执行结果">
            <template #default="{ row }">
              <div style="max-width:300px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ shortJson(row.result) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="指令时间" width="160">
            <template #default="{ row }">
              {{ formatTs(row.send_ts) }}
            </template>
          </el-table-column>
          <!-- <el-table-column label="Created At" width="170">
            <template #default="{ row }">
              {{ row.created_at || '-' }}
            </template>
          </el-table-column> -->
          <!-- <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button type="text" size="small" @click="showDetail(row)">详情</el-button>
            </template>
          </el-table-column> -->
        </el-table>
          <!-- 分页控件 -->
          <div style="margin-top:12px;display:flex;justify-content:flex-end;align-items:center">
            <el-pagination
              background
              :current-page="logsPage"
              :page-size="logsPageSize"
              layout="prev, pager, next, jumper, ->, total"
              :total="logsTotal"
              @current-change="fetchCommandLogs"
            />
          </div>
        </div>
    </el-card>

    <!-- 指令详情弹窗 -->
    <el-dialog v-model:visible="detailVisible" title="指令详情" width="800px">
      <div v-if="detailRow">
        <div style="display:flex;gap:12px;flex-wrap:wrap">
          <div><strong>ID:</strong> {{ detailRow.id }}</div>
          <div><strong>Cmd ID:</strong> {{ detailRow.cmd_id }}</div>
          <div><strong>Device:</strong> {{ detailRow.device_id }}</div>
          <div><strong>Action:</strong> {{ detailRow.action }}</div>
          <div><strong>Status:</strong> <el-tag :type="statusTagType(detailRow.status)">{{ detailRow.status }}</el-tag></div>
          <div><strong>Send TS:</strong> {{ formatTs(detailRow.send_ts) }}</div>
        </div>

        <div style="margin-top:12px">
          <div style="font-weight:600">Params</div>
          <pre style="background:#fafbff;padding:8px;border-radius:4px;max-height:280px;overflow:auto">{{ JSON.stringify(detailRow.params, null, 2) }}</pre>
        </div>
        <div style="margin-top:8px">
          <div style="font-weight:600">Result</div>
          <pre style="background:#fafbff;padding:8px;border-radius:4px;max-height:280px;overflow:auto">{{ JSON.stringify(detailRow.result, null, 2) }}</pre>
        </div>
      </div>
    </el-dialog>

    <!-- 确认弹窗 -->
    <el-dialog v-model:visible="confirmVisible" title="确认下发指令" width="600px">
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
    const snapshotUrl = ref('')
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
      snapshotUrl.value = ''
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
    async function onPrepareSend(){
      try{
        const devicesArr = (selectedDevices && (selectedDevices.value || selectedDevices)) || []
        const hasDevices = Array.isArray(devicesArr) && devicesArr.length>0
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
        // 若是截屏动作，要求仅选择单台设备；多设备截屏应逐台发送
        if(selectedAction.value === 'capture' && Array.isArray(devicesArr) && devicesArr.length !== 1){
          return alert('截屏操作只支持选择单台设备，请仅选择一台设备后重试')
        }
        // 检查所选设备是否在线（仅当 devices 列表里能找到该设备且 status === 'online' 时视为在线）
        const offlineList = (devicesArr || []).filter(id => {
          const dev = devices.value.find(d => d.device_id === id)
          return !dev || dev.status !== 'online'
        })
        if(offlineList.length){
          return alert('以下设备不在线，无法下发指令：' + offlineList.join(', '))
        }
      }catch(e){
        console.error('onPrepareSend error', e)
        return alert('准备发送时发生错误，详见控制台')
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
      // 直接发送，不再弹出确认窗口
      await onSend()
    }

    const finalPayloadPreview = computed(()=>{
      const p = JSON.parse(JSON.stringify(params || {}))
      const targets = (selectedDevices && (selectedDevices.value || selectedDevices)) || []
      const payload = { targets: targets, action: selectedAction.value, params: p, expire_sec: expireSec.value }
      return JSON.stringify(payload,null,2)
    })

    const previewJSON = computed(()=>{
      try{ return JSON.stringify(params,null,2) }catch(e){ return '{}'}
    })

    async function onSend(){
      confirmVisible.value = false
      const devicesArr = (selectedDevices && (selectedDevices.value || selectedDevices)) || []
      if(!Array.isArray(devicesArr) || devicesArr.length===0) return alert('未选择设备')
      sending.value = true
      try{
        const target_device_id = devicesArr.length===1 ? devicesArr[0] : undefined
        const payload = {
          cmd_id: uuidv4(),
          target_device_id: target_device_id,
          device_group_id: undefined,
          target_device_ids: devicesArr.length>1 ? devicesArr : undefined,
          action: selectedAction.value,
          params: JSON.parse(JSON.stringify(params || {})),
          send_ts: Math.floor(Date.now()/1000),
          expire_sec: expireSec.value
        }
        console.debug('onSend payload', payload)
        // 若为截屏动作，直接调用 snapshot 获取 URL（更直接且能即时展示）
        if(selectedAction.value === 'capture' && target_device_id){
          try{
            const snapRes = await api.get(`/v1/devices/remote/${target_device_id}/snapshot`)
            const url = snapRes.data?.snapshot_url || snapRes.data?.url || ''
            if(url) snapshotUrl.value = url
            // 也记录为已下发
            alert('截屏指令已下发: ' + (snapRes.data?.cmd_id || payload.cmd_id))
          }catch(e){
            console.error('snapshot API failed, fallback to sendCommand', e)
            const res = await sendCommand(payload)
            alert('指令已下发: ' + (res.data?.cmd_id || payload.cmd_id))
            const url = res.data?.data?.url || res.data?.url || ''
            if(url) snapshotUrl.value = url
          }
        }else{
          const res = await sendCommand(payload)
          const cmdId = res.data?.cmd_id || payload.cmd_id
          // optimistic feedback
          alert('指令已下发: ' + cmdId)
          // 启动轮询，等待网关/设备回调更新指令状态（非 capture）
          pollCommandStatus(cmdId).catch(e=>{ console.warn('pollCommandStatus error', e) })
        }
        await fetchCommands()
        activeStep.value = 0
      }catch(e){ console.error('onSend failed', e); alert('下发失败：' + (e && e.message || e)) }
      finally{ sending.value = false }
    }

    // 轮询检查指定 cmd_id 的状态（使用 listCommands 查询内存记录）
    async function pollCommandStatus(cmdId, timeoutSec = 30, intervalMs = 1000){
      const start = Date.now()
      while((Date.now() - start) / 1000 < timeoutSec){
        try{
          const r = await listCommands({ limit: 100 })
          const items = r.data?.items || r.data || []
          const rec = items.find(x => x.cmd_id === cmdId)
          if(rec){
            if(rec.status === 'success'){
              // 可选：在前端展示更友好的消息
              alert('指令执行成功: ' + cmdId)
              await fetchCommands()
              return rec
            }
            if(rec.status === 'failed' || rec.status === 'timeout'){
              alert('指令执行失败: ' + cmdId + '，状态：' + rec.status)
              await fetchCommands()
              return rec
            }
          }
        }catch(err){ console.warn('poll error', err) }
        await new Promise(res => setTimeout(res, intervalMs))
      }
      alert('等待指令结果超时: ' + cmdId)
      return null
    }

    async function fetchCommands(){
      try{
        const r = await listCommands({ limit: 30 })
        commands.value = r.data?.items || r.data || []
      }catch(e){ console.warn('fetch commands failed', e) }
    }

    // 指令日志（表格）相关
    const commandLogs = ref([])
    const logsLoading = ref(false)
    const logsPage = ref(1)
    const logsPageSize = ref(20)
    const logsTotal = ref(0)
    // filters for command logs
    const logFilterDevice = ref('')
    const logFilterAction = ref('')

    async function fetchCommandLogs(page = logsPage.value){
      logsLoading.value = true
      try{
        const limit = logsPageSize.value
        const offset = (page - 1) * limit
        // build params with filters
        const params = { limit: limit, offset: offset }
        
        if(logFilterDevice.value) params.device_id = logFilterDevice.value
        if(logFilterAction.value) params.action = logFilterAction.value
        // time filter removed from UI; backend still supports from_ts/to_ts if needed
        const r = await listCommands(params)
        const items = r.data?.items || r.data || []
        logsTotal.value = r.data?.total ?? (Array.isArray(items) ? items.length : 0)
        commandLogs.value = (items || []).map(it => ({
          id: it.id || it._id || it.db_id || it.cmd_id,
          cmd_id: it.cmd_id,
          device_id: it.device_id || it.target_device_id || (it.target_device_ids && Array.isArray(it.target_device_ids)? it.target_device_ids.join(',') : undefined),
          action: it.action,
          params: it.params || it.params_json || it.params || it.params_text || it.params,
          status: it.status,
          result: it.result || it.data || it.response || '',
          send_ts: it.send_ts,
          created_at: it.created_at,
          updated_at: it.updated_at
        }))
        logsPage.value = page
      }catch(e){ console.warn('fetch command logs failed', e) }
      finally{ logsLoading.value = false }
    }

    function clearLogFilters(){
      // former clear button now acts as refresh; keep for compatibility
      fetchCommandLogs(logsPage.value)
    }

    function shortJson(v){
      try{
        if(v===null||v===undefined) return '-'
        const s = typeof v === 'string' ? v : JSON.stringify(v)
        return s.length>120 ? s.slice(0,120)+'...' : s
      }catch(e){ return '-' }
    }

    // 缓存
    const materialNames = reactive({})
    async function ensureMaterialName(id){
      try{
        if(!id) return
        if(materialNames[id] !== undefined) return
        // 先在已加载的 materials 中查找
        const fromList = (materials.value || []).find(m => m.material_id === id)
        if(fromList){ materialNames[id] = fromList.file_name || fromList.material_id; return }
        // 后端按 q 查询，尽量找到匹配项
        const r = await api.get('/v1/materials', { params: { q: id, page: 1, page_size: 5 } }).catch(()=>null)
        const items = r && (r.data?.items || r.data) || []
        const found = (Array.isArray(items) ? items.find(it => it.material_id === id) : null) || (Array.isArray(items) && items[0])
        materialNames[id] = found ? (found.file_name || found.material_id) : id
      }catch(e){ materialNames[id] = id }
    }

    // 将 params/result 按动作格式化为中文可读文本
    function formatParams(action, params){
      try{
        if(params===null||params===undefined) return '-'
        let p = params
        if(typeof p === 'string'){
          try{ p = JSON.parse(p) }catch(e){ /* keep as string */ }
        }
        if(action === 'set_volume'){
          if(p.volume !== undefined) return `声音调整至：${p.volume}`
          if(p.mute !== undefined) return p.mute ? '静音' : '取消静音'
          return shortJson(p)
        }
        if(action === 'reboot'){
          return '重启设备'
        }
        if(action === 'capture'){
          if(p.save_to) return `截屏并保存至：${p.save_to}`
          return '截屏请求'
        }
        if(action === 'insert_play'){
          if(p.material_id){
            const mid = p.material_id
            const name = materialNames[mid]
            if(name) return `插播素材：${name}`
            // 后台异步加载名称以便下次显示更友好
            ensureMaterialName(mid)
            return `插播素材：${mid}`
          }
          return shortJson(p)
        }
        // 默认展示常见字段或简短 JSON
        if(typeof p === 'object'){
          if(p.volume !== undefined) return `声音：${p.volume}`
          if(p.material_id) return `素材：${p.material_id}`
          if(p.save_to) return `保存到：${p.save_to}`
          return shortJson(p)
        }
        return String(p)
      }catch(e){ return shortJson(params) }
    }

    const detailVisible = ref(false)
    const detailRow = ref(null)
    function showDetail(r){ detailRow.value = r; detailVisible.value = true }

    function formatTs(ts){ if(!ts) return ''; try{ return new Date(ts*1000).toLocaleString() }catch(e){ return ts } }

    onMounted(()=>{
      // prefill from query
      if(route.query.target_device_id){ selectedDevices.value = [route.query.target_device_id] }
      fetchDevices(); fetchCommands()
      fetchCommandLogs()
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
      formatTs,
      formatParams,
      // log filters
      logFilterDevice, logFilterAction, clearLogFilters,
      actions, selectedAction, selectAction, previewTemplate, actionTitle, paramTemplate, params, fieldComponent,
      resetParams, expireSec, onPrepareSend, confirmVisible, finalPayloadPreview, onSend, sending, previewOnly, snapshotUrl,
      materials, materialQuery, materialLoading, materialsFiltered, selectMaterial, selectedMaterial, onPreviewMaterial, fetchMaterials, onMaterialQueryChange, materialItemStyle,
      commands, previewJSON, fetchCommands
      , commandLogs, logsLoading, fetchCommandLogs, shortJson, detailVisible, detailRow, showDetail,
      logsPage, logsPageSize, logsTotal
    }
  }
}
</script>

<style scoped>
.device-row:hover{ box-shadow: 0 6px 18px rgba(47,140,255,0.04); transform: translateY(-2px); }
 .ability-card.selected{ box-shadow: 0 10px 30px rgba(47,140,255,0.08); border-color: rgba(47,140,255,0.14); transform: translateY(-2px); }
</style>
