<template>
  <div class="commands-page" style="padding:16px">
    <el-card>
      <h3>发送指令</h3>
      <el-form :model="form" label-width="120px">
        <el-form-item label="目标设备ID">
          <el-input v-model="form.target_device_id" placeholder="例如：ELEV_001"/>
        </el-form-item>
        <el-form-item label="目标设备组ID">
          <el-input v-model="form.device_group_id" placeholder="选填"/>
        </el-form-item>
        <el-form-item label="动作">
          <el-select v-model="form.action" placeholder="请选择动作">
            <el-option label="重启" value="reboot"/>
            <el-option label="设置音量" value="set_volume"/>
            <el-option label="截屏" value="capture"/>
            <el-option label="视频插播" value="insert_play"/>
          </el-select>
        </el-form-item>
        <el-form-item label="参数（JSON）">
          <el-input type="textarea" :rows="6" v-model="form.params_text" placeholder='{"volume": 60}'/>
        </el-form-item>
        <el-form-item label="过期时间（秒）">
          <el-input-number v-model="form.expire_sec" :min="1"/>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onSend" :loading="sending">发送</el-button>
          <el-button @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card style="margin-top:16px">
      <h3>近期指令</h3>
      <el-table :data="commands" style="width:100%">
        <el-table-column prop="cmd_id" label="指令ID"/>
        <el-table-column prop="target_device_id" label="目标" width="180"/>
        <el-table-column prop="action" label="动作" width="140"/>
        <el-table-column prop="status" label="状态" width="120"/>
        <el-table-column prop="send_ts" label="下发时间" width="180"/>
        <el-table-column label="结果" width="220">
          <template #default="{ row }">
            <pre style="white-space:pre-wrap;max-height:120px;overflow:auto">{{ row.result }}</pre>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import { ref, reactive, onMounted, watch } from 'vue'
import { sendCommand, listCommands } from '../api/commands'
import { useRoute } from 'vue-router'

function uuidv4(){
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c=>{
    const r = Math.random()*16|0, v = c=='x'? r: (r&0x3|0x8)
    return v.toString(16)
  })
}

export default {
  setup(){
    const form = reactive({
      target_device_id: '',
      device_group_id: '',
      action: '',
      params_text: '{}',
      expire_sec: 60,
    })
    const route = useRoute()
    const sending = ref(false)
    const commands = ref([])

    async function fetchCommands(){
      try{
        const r = await listCommands({ limit: 20 })
        commands.value = r.data?.items || r.data || []
      }catch(e){ console.warn('fetch commands failed', e) }
    }

    async function onSend(){
      // validate
      if(!form.action){ return alert('请选择动作') }
      if(!form.target_device_id && !form.device_group_id){ return alert('请填写目标设备ID或设备组ID') }
      let params
      try{ params = JSON.parse(form.params_text || '{}') }catch(e){ return alert('参数 JSON 解析失败') }

      const payload = {
        cmd_id: uuidv4(),
        target_device_id: form.target_device_id || undefined,
        device_group_id: form.device_group_id || undefined,
        action: form.action,
        params,
        send_ts: Math.floor(Date.now()/1000),
        expire_sec: form.expire_sec
      }

      sending.value = true
      try{
        const res = await sendCommand(payload)
        alert('指令已下发: ' + (res.data?.cmd_id || payload.cmd_id))
        await fetchCommands()
      }catch(e){
        console.error(e)
        alert('下发失败')
      }finally{ sending.value = false }
    }

    function onReset(){
      form.target_device_id=''; form.device_group_id=''; form.action=''; form.params_text='{}'; form.expire_sec=60
    }

    onMounted(()=>{
      // prefill from query (when navigated from device list)
      if(route.query.target_device_id){ form.target_device_id = route.query.target_device_id }
      if(route.query.device_group_id){ form.device_group_id = route.query.device_group_id }
      fetchCommands()
    })

    // update form if route query changes
    watch(()=>route.query, (q)=>{
      if(q.target_device_id) form.target_device_id = q.target_device_id
      if(q.device_group_id) form.device_group_id = q.device_group_id
    })

    return { form, sending, onSend, onReset, commands }
  }
}
</script>
