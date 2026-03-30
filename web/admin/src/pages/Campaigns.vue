<template>
  <div class="campaign-page">
    <section class="hero-card">
        <h2>投放策略中心</h2>
        
      <div class="hero-actions">
        <el-button @click="fetchCampaigns">刷新</el-button>
        <el-button type="primary" @click="openCreateDialog">新建策略</el-button>
      </div>
    </section>

    <section class="stats-grid">
      <el-card class="stat-card">
        <div class="stat-label">策略总数</div>
        <div class="stat-value">{{ summary.total }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">待发布</div>
        <div class="stat-value">{{ summary.draft }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">已发布</div>
        <div class="stat-value">{{ summary.published }}</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">最近失败设备</div>
        <div class="stat-value">{{ summary.recentFailed }}</div>
      </el-card>
    </section>

    <el-card class="table-card">
      <template #header>
        <div class="table-toolbar">
          <el-input
            v-model="keyword"
            clearable
            placeholder="按策略号/名称/版本筛选"
            style="max-width: 360px"
          />
          <el-tag type="info">共 {{ filteredCampaigns.length }} 条</el-tag>
        </div>
      </template>

      <el-table :data="filteredCampaigns" v-loading="loading" style="width: 100%">
        <el-table-column prop="campaign_id" label="策略号" width="180" />
        <el-table-column prop="name" label="策略名" min-width="180" />
        <el-table-column prop="creator_id" label="创建者" width="120" />
        <el-table-column prop="version" label="版本" width="120" />
        <el-table-column label="目标设备" width="110">
          <template #default="{ row }">{{ deviceCount(row) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'published' ? 'success' : 'warning'">
              {{ formatCampaignStatus(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ formatDate(row.updated_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="400" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button link type="primary" @click="openEditDialog(row)">修改</el-button>
            <el-button link type="primary" @click="publishNow(row)">发布</el-button>
            <el-button link type="primary" @click="openLogs(row)">发布日志</el-button>
            <el-button link type="primary" @click="openVersions(row)">版本管理</el-button>
            <el-button link type="danger" @click="deleteCampaignRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" width="86%" top="4vh" destroy-on-close>
      <template #header>
        <div class="dialog-title">策略详情 - {{ detailCampaign?.campaign_id }}</div>
      </template>

      <el-tabs v-model="detailTab">
        <el-tab-pane label="概览" name="overview">
          <el-descriptions :column="3" border>
            <el-descriptions-item label="策略名称">{{ detailCampaign?.name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="创建人">{{ detailCampaign?.creator_id || '-' }}</el-descriptions-item>
            <el-descriptions-item label="当前状态">{{ formatCampaignStatus(detailCampaign?.status) }}</el-descriptions-item>
            <el-descriptions-item label="版本号">{{ detailCampaign?.version || '-' }}</el-descriptions-item>
            <el-descriptions-item label="生效开始时间">{{ formatDate(detailCampaign?.start_at) }}</el-descriptions-item>
            <el-descriptions-item label="生效结束时间">{{ formatDate(detailCampaign?.end_at) }}</el-descriptions-item>
          </el-descriptions>

          <h4 class="section-title">目标设备</h4>
          <div class="tag-wrap">
            <el-tag v-for="d in detailDevices" :key="d" type="info" effect="plain">{{ d }}</el-tag>
            <span v-if="!detailDevices.length" class="muted">暂无目标设备</span>
          </div>

          <h4 class="section-title">素材播放清单</h4>
          <el-table :data="detailPlaylist" size="small" border>
            <el-table-column label="广告名" min-width="180">
              <template #default="{ row }">{{ materialNameById(row.id) || row.file || '-' }}</template>
            </el-table-column>
            <el-table-column label="广告商" min-width="160">
              <template #default="{ row }">{{ materialAdvertiserById(row.id) || '-' }}</template>
            </el-table-column>
            <el-table-column prop="priority" label="播放优先级" width="110" />
            <el-table-column label="投放时段" min-width="180">
              <template #default="{ row }">
                <el-tag v-for="s in row.slots || []" :key="s" size="small" class="mr8">{{ s }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="终端执行视图" name="edge">
          <el-row :gutter="12" style="margin-bottom: 12px">
            <el-col :span="8"><el-card class="mini-card">策略标识: {{ detailEdgeSchedule?.policy_id || '-' }}</el-card></el-col>
            <el-col :span="8"><el-card class="mini-card">策略生效日期: {{ detailEdgeSchedule?.effective_date || '-' }}</el-card></el-col>
            <el-col :span="8"><el-card class="mini-card">素材下载基地址: {{ detailEdgeSchedule?.download_base_url || '-' }}</el-card></el-col>
          </el-row>

          <el-descriptions :column="3" border>
            <el-descriptions-item label="默认音量">{{ edgeGlobal.default_volume }}</el-descriptions-item>
            <el-descriptions-item label="下载重试次数">{{ edgeGlobal.download_retry_count }}</el-descriptions-item>
            <el-descriptions-item label="状态上报间隔秒">{{ edgeGlobal.report_interval_sec }}</el-descriptions-item>
          </el-descriptions>

          <h4 class="section-title">时段规则</h4>
          <el-table :data="edgeTimeSlots" size="small" border>
            <el-table-column prop="slot_id" label="时段编号" width="100" />
            <el-table-column label="时间范围" width="170">
              <template #default="{ row }">
                <el-tag :type="row.slot_id === 99 ? 'warning' : 'info'" effect="plain">{{ row.time_range }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="priority" label="优先级" width="90" />
            <el-table-column prop="volume" label="播放音量" width="100" />
            <el-table-column prop="loop_mode" label="循环模式" width="130" />
            <el-table-column label="播放列表" min-width="220">
              <template #default="{ row }">
                <el-tag v-for="id in row.playlist || []" :key="id" size="small" class="mr8">{{ id }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="中断策略" name="interrupts">
          <el-table :data="edgeInterrupts" size="small" border>
            <el-table-column prop="trigger_type" label="触发类型" width="140" />
            <el-table-column prop="ad_id" label="插播素材编号" min-width="180" />
            <el-table-column prop="priority" label="优先级" width="100" />
            <el-table-column prop="play_mode" label="播放模式" min-width="140" />
          </el-table>
          <el-empty v-if="!edgeInterrupts.length" description="当前策略未设置中断策略" />
        </el-tab-pane>
      </el-tabs>
    </el-dialog>

    <el-dialog v-model="logsVisible" width="80%" destroy-on-close>
      <template #header>
        <div class="dialog-title">发布日志 - {{ activeCampaignId }}</div>
      </template>
      <div class="table-toolbar" style="margin-bottom: 12px">
        <div>
          <el-tag class="mr8">total: {{ publishLogs.total }}</el-tag>
          <el-tag type="success" class="mr8">success: {{ publishLogs.success }}</el-tag>
          <el-tag type="danger">failed: {{ publishLogs.failed }}</el-tag>
        </div>
        <div>
          <el-button @click="refreshLogs">刷新日志</el-button>
          <el-button type="warning" :disabled="publishLogs.failed < 1" @click="retryFailedDevices">重试失败设备</el-button>
        </div>
      </div>
      <el-table :data="publishLogs.items" size="small" border>
        <el-table-column prop="batch_id" label="batch_id" width="150" />
        <el-table-column prop="device_id" label="device_id" width="150" />
        <el-table-column label="ok" width="80">
          <template #default="{ row }">
            <el-tag :type="row.ok ? 'success' : 'danger'">{{ row.ok ? 'true' : 'false' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="error" min-width="220" />
        <el-table-column label="created_at" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="versionsVisible" width="72%" destroy-on-close>
      <template #header>
        <div class="dialog-title">版本管理 - {{ activeCampaignId }}</div>
      </template>
      <div class="table-toolbar" style="margin-bottom: 12px">
        <el-switch
          v-model="rollbackPublishNow"
          active-text="回滚后立即发布"
          inactive-text="仅回滚不发布"
        />
        <el-button @click="refreshVersions">刷新版本</el-button>
      </div>
      <el-table :data="versionList.items" size="small" border>
        <el-table-column prop="version" label="version" width="160" />
        <el-table-column label="created_at" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="素材数" width="90">
          <template #default="{ row }">{{ versionPlaylistCount(row) }}</template>
        </el-table-column>
        <el-table-column label="中断数" width="90">
          <template #default="{ row }">{{ versionInterruptCount(row) }}</template>
        </el-table-column>
        <el-table-column label="下载地址" min-width="180">
          <template #default="{ row }">{{ versionDownloadBaseUrl(row) }}</template>
        </el-table-column>
        <el-table-column label="版本内容" min-width="180">
          <template #default="{ row }">
            <el-button link type="primary" @click="showVersionDetail(row)">查看版本详情</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button link type="danger" @click="rollbackVersion(row)">回滚到此版本</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="createVisible" width="90%" max-height="90vh" destroy-on-close>
      <template #header>
        <div class="dialog-title">{{ isEditMode ? '修改投放策略' : '新建投放策略' }}</div>
      </template>

      <div class="create-form-wrapper">
        <el-form :model="createForm" label-width="100px" size="default">
          <el-row v-if="isEditMode" :gutter="16" style="margin-bottom: 10px">
            <el-col :span="12">
              <el-form-item label="策略号">
                <el-input :model-value="editingCampaignId" disabled />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="版本号">
                <el-input :model-value="editingVersion" disabled />
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 基础信息 -->
          <el-divider content-position="left">基础信息</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="策略名">
                <el-input v-model="createForm.name" placeholder="" clearable />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="isEditMode ? '修改者' : '创建者'">
                <el-input v-model="createForm.creator_id" placeholder="" clearable />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="24">
              <el-form-item label="下载地址">
                <el-input
                  v-model="createForm.download_base_url"
                  placeholder=""
                  clearable
                />
                <small style="color: #909399; display: block; margin-top: 4px">
                  广告素材文件的下载服务器地址，会与文件名拼接成完整 URL
                </small>
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 设备选择 -->
          <el-divider content-position="left">目标设备选择</el-divider>
          <el-form-item label="选择设备">
            <div class="device-select-layout">
              <div class="device-select-main">
                <div class="device-search-row">
                  <el-input
                    v-model="deviceSearchKeyword"
                    placeholder="搜索设备"
                    clearable
                  />
                  <el-button size="small" @click="selectFilteredDevices">全选</el-button>
                </div>
                <div class="device-selector">
                  <div class="device-list">
                    <el-checkbox
                      v-for="dev in filteredDeviceList"
                      :key="dev"
                      v-model="createForm.devicesSelected"
                      :label="dev"
                      style="display: block; margin-bottom: 8px"
                    />
                  </div>
                  <div v-if="!filteredDeviceList.length" style="color: #909399; padding: 10px; text-align: center">
                    无匹配设备
                  </div>
                </div>
                <div v-if="createForm.devicesSelected.length" style="margin-top: 12px">
                  <span style="font-size: 12px; color: #606266">已选设备:</span>
                  <el-tag
                    v-for="dev in createForm.devicesSelected"
                    :key="dev"
                    closable
                    @close="removeDevice(dev)"
                    style="margin: 4px 4px 4px 0"
                  >
                    {{ dev }}
                  </el-tag>
                </div>
              </div>
              <div class="device-select-side">
                <el-button
                  type="danger"
                  plain
                  size="small"
                  :disabled="!createForm.devicesSelected.length"
                  @click="clearSelectedDevices"
                >
                  清空所选设备
                </el-button>
              </div>
            </div>
          </el-form-item>

          <!-- 素材列表 -->
          <el-divider content-position="left">素材播放列表</el-divider>
          <el-form-item label="投放方式">
            <el-radio-group v-model="createForm.deliveryMode">
              <el-radio label="random">随机播放</el-radio>
              <el-radio label="specified">指定播放</el-radio>
            </el-radio-group>
          </el-form-item>

          <div v-if="createForm.deliveryMode === 'specified'" style="margin-bottom: 12px">
            <el-button type="primary" size="small" @click="addAdRow">+ 添加素材</el-button>
          </div>
          <el-alert
            v-else
            title="随机播放模式下将从素材库中随机选择素材播放"
            type="info"
            :closable="false"
            style="margin-bottom: 12px"
          />

          <el-table v-if="createForm.deliveryMode === 'specified'" :data="createForm.adsList" border size="small" class="form-table">
            <el-table-column label="广告ID（可搜索）" width="200">
              <template #default="{ row, $index }">
                <el-select
                  v-model="row.adId"
                  filterable
                  clearable
                  placeholder="点击选择广告"
                  @change="(val) => onAdSelect($index, val)"
                  style="width: 100%"
                >
                  <el-option v-for="mat in materials" :key="mat.material_id" :label="`${mat.file_name}-${mat.advertiser}`" :value="mat.material_id" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="优先级" width="110">
              <template #default="{ row }">
                <el-input-number
                  v-model="row.priority"
                  :min="1"
                  :max="100"
                  size="small"
                  controls-position="right"
                  style="width: 100%"
                />
              </template>
            </el-table-column>
            <el-table-column label="时间段（必选）" min-width="240">
              <template #default="{ row }">
                <el-select
                  v-model="row.slots"
                  multiple
                  placeholder="点击选择时段"
                  style="width: 100%"
                >
                  <el-optgroup label="常用时段">
                    <el-option label="08:00-10:00" value="08:00-10:00" />
                    <el-option label="12:00-14:00" value="12:00-14:00" />
                    <el-option label="17:00-19:00" value="17:00-19:00" />
                    <el-option label="19:00-21:00" value="19:00-21:00" />
                  </el-optgroup>
                  <el-optgroup label="自定义">
                    <el-option label="全天(*)" value="*" />
                  </el-optgroup>
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="removeAdRow($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 紧急插播策略 -->
          <el-divider content-position="left">紧急插播策略（可选）</el-divider>
          <div style="margin-bottom: 12px">
            <el-button type="primary" size="small" @click="addInterruptRow">+ 添加中断策略</el-button>
            <small style="margin-left: 8px; color: #909399">优先级建议 ≥ 100 以确保打断普通播放</small>
          </div>
          <el-table v-if="createForm.interruptsList.length" :data="createForm.interruptsList" border size="small" class="form-table">
            <el-table-column label="触发类型" width="120">
              <template #default="{ row }">
                <el-select v-model="row.trigger_type" style="width: 100%">
                  <el-option label="command（命令）" value="command" />
                  <el-option label="signal（信号）" value="signal" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="广告ID（可搜索）" width="160">
              <template #default="{ row }">
                <el-select
                  v-model="row.ad_id"
                  filterable
                  placeholder="点击选择广告"
                  style="width: 100%"
                >
                  <el-option v-for="mat in materials" :key="mat.material_id" :label="`${mat.file_name}-${mat.advertiser}`" :value="mat.material_id" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="优先级" width="120">
              <template #default="{ row }">
                <el-input-number
                  v-model="row.priority"
                  :min="1"
                  :max="999"
                  size="small"
                  controls-position="right"
                  style="width: 100%"
                />
              </template>
            </el-table-column>
            <el-table-column label="播放模式" width="140">
              <template #default="{ row }">
                <el-select v-model="row.play_mode" style="width: 100%">
                  <el-option label="loop_until_stop" value="loop_until_stop" />
                  <el-option label="loop_with_count" value="loop_with_count" />
                  <el-option label="single_play" value="single_play" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="removeInterruptRow($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!createForm.interruptsList.length" style="padding: 12px; text-align: center; color: #909399">
            暂无中断策略
          </div>
          <div v-if="interruptErrors.length" style="margin-top: 8px; color: #f56c6c">
            <span v-for="err in interruptErrors" :key="err" style="display: block">⚠ {{ err }}</span>
          </div>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">{{ isEditMode ? '提交修改' : '创建策略' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import campaignApi from '../api/campaigns'
import materialsApi from '../api/materials'

export default {
  setup() {
    const campaigns = ref([])
    const loading = ref(false)
    const keyword = ref('')

    const detailVisible = ref(false)
    const detailTab = ref('overview')
    const detailCampaign = ref(null)
    const detailScheduleConfig = ref(null)
    const detailEdgeSchedule = ref(null)

    const logsVisible = ref(false)
    const versionsVisible = ref(false)
    const activeCampaignId = ref('')
    const publishLogs = ref({ total: 0, success: 0, failed: 0, items: [] })
    const versionList = ref({ total: 0, items: [] })
    const rollbackPublishNow = ref(true)

    const createVisible = ref(false)
    const isEditMode = ref(false)
    const editingCampaignId = ref('')
    const editingVersion = ref('')
    const creating = ref(false)
    const materials = ref([])
    const deviceSearchKeyword = ref('')
    const allDevices = ref([])
    const adErrors = ref([])
    const interruptErrors = ref([])

    const createForm = ref({
      name: 'morning_campaign',
      creator_id: 'u_1',
      download_base_url: 'https://oss.aliyun.com/ads/',
      deliveryMode: 'specified',
      devicesSelected: [],
      adsList: [
        {
          adId: '',
          file: '',
          md5: '',
          priority: 10,
          slots: []
        }
      ],
      interruptsList: []
    })

    const filteredCampaigns = computed(() => {
      const key = keyword.value.trim().toLowerCase()
      if (!key) return campaigns.value
      return campaigns.value.filter((item) => {
        const blob = [item.campaign_id, item.name, item.version, item.status].join(' ').toLowerCase()
        return blob.includes(key)
      })
    })

    const filteredDeviceList = computed(() => {
      const key = deviceSearchKeyword.value.trim().toLowerCase()
      if (!key) return allDevices.value
      return allDevices.value.filter(dev => dev.toLowerCase().includes(key))
    })

    const summary = computed(() => {
      const total = campaigns.value.length
      const draft = campaigns.value.filter((x) => x.status === 'draft').length
      const published = campaigns.value.filter((x) => x.status === 'published').length
      let recentFailed = 0
      if (publishLogs.value && publishLogs.value.failed) {
        recentFailed = publishLogs.value.failed
      }
      return { total, draft, published, recentFailed }
    })

    const detailPlaylist = computed(() => detailScheduleConfig.value?.playlist || [])
    const detailDevices = computed(() => normalizeDevices(detailCampaign.value?.target_device_groups))
    const edgeGlobal = computed(() => detailEdgeSchedule.value?.global_config || {})
    const edgeTimeSlots = computed(() => detailEdgeSchedule.value?.time_slots || [])
    const edgeInterrupts = computed(() => detailEdgeSchedule.value?.interrupts || [])

    function normalizeDevices(raw) {
      if (!raw) return []
      if (Array.isArray(raw)) return raw.filter((x) => typeof x === 'string' && x.trim())
      if (typeof raw === 'string') {
        try {
          const parsed = JSON.parse(raw)
          if (Array.isArray(parsed)) return parsed.filter((x) => typeof x === 'string' && x.trim())
          return raw
            .split(/[\n,]/)
            .map((x) => x.trim())
            .filter(Boolean)
        } catch (_e) {
          return raw
            .split(/[\n,]/)
            .map((x) => x.trim())
            .filter(Boolean)
        }
      }
      return []
    }

    function deviceCount(row) {
      return normalizeDevices(row.target_device_groups).length
    }

    function formatDate(v) {
      if (!v) return '-'
      const d = new Date(v)
      if (Number.isNaN(d.getTime())) return String(v)
      return d.toLocaleString()
    }

    function formatCampaignStatus(status) {
      if (status === 'draft') return '待发布'
      if (status === 'published') return '已发布'
      return status || '未知状态'
    }

    function pretty(v) {
      try {
        return JSON.stringify(v || {}, null, 2)
      } catch (_e) {
        return String(v)
      }
    }

    function parseScheduleJson(raw) {
      if (!raw) return {}
      if (typeof raw === 'string') {
        try {
          return JSON.parse(raw)
        } catch (_e) {
          return {}
        }
      }
      return typeof raw === 'object' ? raw : {}
    }

    function versionPlaylistCount(row) {
      const schedule = parseScheduleJson(row?.schedule_json)
      return Array.isArray(schedule.playlist) ? schedule.playlist.length : 0
    }

    function versionInterruptCount(row) {
      const schedule = parseScheduleJson(row?.schedule_json)
      return Array.isArray(schedule.interrupts) ? schedule.interrupts.length : 0
    }

    function versionDownloadBaseUrl(row) {
      const schedule = parseScheduleJson(row?.schedule_json)
      return schedule.download_base_url || '-'
    }

    function materialById(materialId) {
      return materials.value.find(m => m.material_id === materialId)
    }

    function materialNameById(materialId) {
      const mat = materialById(materialId)
      return mat?.file_name || ''
    }

    function materialAdvertiserById(materialId) {
      const mat = materialById(materialId)
      return mat?.advertiser || ''
    }

    async function fetchCampaigns() {
      loading.value = true
      try {
        const data = await campaignApi.listCampaigns({ limit: 200, offset: 0 })
        campaigns.value = data?.items || []
      } catch (e) {
        campaigns.value = []
        ElMessage.error('加载策略列表失败')
      } finally {
        loading.value = false
      }
    }

    async function openDetail(row) {
      try {
        const [campaign, scheduleConfig, edgeSchedule] = await Promise.all([
          campaignApi.getCampaign(row.campaign_id),
          campaignApi.getScheduleConfig(row.campaign_id),
          campaignApi.getEdgeSchedule(row.campaign_id),
        ])
        detailCampaign.value = campaign
        detailScheduleConfig.value = scheduleConfig
        detailEdgeSchedule.value = edgeSchedule
        detailTab.value = 'overview'
        detailVisible.value = true
      } catch (e) {
        ElMessage.error('加载策略详情失败')
      }
    }

    async function publishNow(row) {
      try {
        await ElMessageBox.confirm(`确定发布策略 ${row.campaign_id} 吗？`, '发布确认', {
          confirmButtonText: '发布',
          cancelButtonText: '取消',
          type: 'warning',
        })
      } catch (_e) {
        return
      }

      try {
        const res = await campaignApi.publishCampaign(row.campaign_id)
        const pushed = res?.pushed ?? 0
        const total = res?.total ?? 0
        const msg = res?.idempotent ? '该版本已发布，无需重复下发' : `发布完成 ${pushed}/${total}`
        ElMessage.success(msg)
        await fetchCampaigns()
      } catch (e) {
        const detail = e?.response?.data?.detail
        if (detail?.errors && Array.isArray(detail.errors)) {
          ElMessage.error(`发布校验失败: ${detail.errors.join(' ; ')}`)
          return
        }
        ElMessage.error('发布失败')
      }
    }

    async function deleteCampaignRow(row) {
      try {
        await ElMessageBox.confirm(
          `确定删除策略 ${row.campaign_id} 吗？删除后不可恢复。`,
          '删除确认',
          {
            confirmButtonText: '删除',
            cancelButtonText: '取消',
            type: 'warning',
          }
        )
      } catch (_e) {
        return
      }

      try {
        await campaignApi.deleteCampaign(row.campaign_id)
        ElMessage.success('删除成功')
        await fetchCampaigns()
      } catch (e) {
        const detail = e?.response?.data?.detail
        const errMsg = typeof detail === 'string' ? detail : (detail?.message || '删除失败')
        ElMessage.error(errMsg)
      }
    }

    async function openLogs(row) {
      activeCampaignId.value = row.campaign_id
      logsVisible.value = true
      await refreshLogs()
    }

    async function refreshLogs() {
      if (!activeCampaignId.value) return
      try {
        const data = await campaignApi.listPublishLogs(activeCampaignId.value, { limit: 200, offset: 0 })
        publishLogs.value = {
          total: data?.total || 0,
          success: data?.success || 0,
          failed: data?.failed || 0,
          items: data?.items || []
        }
      } catch (e) {
        publishLogs.value = { total: 0, success: 0, failed: 0, items: [] }
        ElMessage.error('读取发布日志失败')
      }
    }

    async function retryFailedDevices() {
      if (!activeCampaignId.value) return
      try {
        const res = await campaignApi.retryFailed(activeCampaignId.value)
        if (res?.idempotent) {
          ElMessage.warning('该批次已重试过，未重复执行')
        } else {
          ElMessage.success(`重试完成，成功 ${res?.pushed || 0}/${res?.retried || 0}`)
        }
        await refreshLogs()
      } catch (e) {
        ElMessage.error('重试失败设备失败')
      }
    }

    async function openVersions(row) {
      activeCampaignId.value = row.campaign_id
      versionsVisible.value = true
      await refreshVersions()
    }

    async function refreshVersions() {
      if (!activeCampaignId.value) return
      try {
        const data = await campaignApi.listVersions(activeCampaignId.value, { limit: 100, offset: 0 })
        versionList.value = {
          total: data?.total || 0,
          items: data?.items || []
        }
      } catch (e) {
        versionList.value = { total: 0, items: [] }
        ElMessage.error('读取版本历史失败')
      }
    }

    async function rollbackVersion(row) {
      try {
        await ElMessageBox.confirm(
          `确定回滚到版本 ${row.version} 吗？`,
          '回滚确认',
          { type: 'warning', confirmButtonText: '回滚', cancelButtonText: '取消' }
        )
      } catch (_e) {
        return
      }

      try {
        const res = await campaignApi.rollbackCampaign(activeCampaignId.value, {
          version: row.version,
          publish_now: rollbackPublishNow.value,
        })
        if (res?.idempotent) {
          ElMessage.warning('回滚版本已在目标设备发布过，本次未重复下发')
        } else {
          ElMessage.success('回滚成功')
        }
        await refreshVersions()
        await fetchCampaigns()
      } catch (e) {
        const detail = e?.response?.data?.detail
        if (detail?.errors && Array.isArray(detail.errors)) {
          ElMessage.error(`回滚校验失败: ${detail.errors.join(' ; ')}`)
          return
        }
        ElMessage.error('回滚失败')
      }
    }

    function showVersionDetail(row) {
      const schedule = parseScheduleJson(row?.schedule_json)
      const playlist = Array.isArray(schedule.playlist) ? schedule.playlist : []
      const interrupts = Array.isArray(schedule.interrupts) ? schedule.interrupts : []
      const summary = {
        version: row?.version || '-',
        created_at: row?.created_at || '-',
        download_base_url: schedule.download_base_url || '-',
        playlist_count: playlist.length,
        interrupts_count: interrupts.length,
      }

      ElMessageBox.alert(`<pre style="max-height:56vh;overflow:auto">${escapeHtml(pretty(summary))}\n\n${escapeHtml(pretty(schedule))}</pre>`, `版本 ${row.version}`, {
        dangerouslyUseHTMLString: true,
        confirmButtonText: '关闭',
      })
    }

    function escapeHtml(str) {
      return str
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
    }

    function openCreateDialog() {
      resetCreateForm()
      isEditMode.value = false
      editingCampaignId.value = ''
      editingVersion.value = ''
      createVisible.value = true
    }

    async function openEditDialog(row) {
      try {
        const [campaign, scheduleConfig] = await Promise.all([
          campaignApi.getCampaign(row.campaign_id),
          campaignApi.getScheduleConfig(row.campaign_id),
        ])

        resetCreateForm()
        isEditMode.value = true
        editingCampaignId.value = row.campaign_id
        editingVersion.value = campaign?.version || row.version || '-'

        createForm.value.name = campaign?.name || row.name || ''
        createForm.value.creator_id = ''
        createForm.value.download_base_url = scheduleConfig?.download_base_url || createForm.value.download_base_url
        createForm.value.devicesSelected = normalizeDevices(campaign?.target_device_groups)
        createForm.value.deliveryMode = 'specified'

        const playlist = Array.isArray(scheduleConfig?.playlist) ? scheduleConfig.playlist : []
        createForm.value.adsList = playlist.length
          ? playlist.map(item => ({
            adId: item.id || '',
            file: item.file || '',
            md5: item.md5 || '',
            priority: Number(item.priority || 10),
            slots: Array.isArray(item.slots) ? item.slots : []
          }))
          : [{ adId: '', file: '', md5: '', priority: 10, slots: [] }]

        const interrupts = Array.isArray(scheduleConfig?.interrupts) ? scheduleConfig.interrupts : []
        createForm.value.interruptsList = interrupts.map(item => ({
          trigger_type: item.trigger_type || 'command',
          ad_id: item.ad_id || '',
          priority: Number(item.priority || 100),
          play_mode: item.play_mode || 'loop_until_stop'
        }))

        createVisible.value = true
      } catch (_e) {
        ElMessage.error('加载策略编辑信息失败')
      }
    }

    function resetCreateForm() {
      createForm.value = {
        name: 'morning_campaign',
        creator_id: 'u_1',
        download_base_url: 'https://oss.aliyun.com/ads/',
        deliveryMode: 'specified',
        devicesSelected: [],
        adsList: [
          {
            adId: '',
            file: '',
            md5: '',
            priority: 10,
            slots: []
          }
        ],
        interruptsList: []
      }
      adErrors.value = []
      interruptErrors.value = []
      deviceSearchKeyword.value = ''
    }

    function addAdRow() {
      createForm.value.adsList.push({
        adId: '',
        file: '',
        md5: '',
        priority: 10,
        slots: []
      })
    }

    function removeAdRow(idx) {
      createForm.value.adsList.splice(idx, 1)
    }

    function onAdSelect(idx, adId) {
      const row = createForm.value.adsList[idx]
      if (!adId) {
        row.file = ''
        row.md5 = ''
        return
      }

      // 查找对应的素材并自动填充 file 和 md5
      const material = materials.value.find(m => m.material_id === adId)
      if (material) {
        row.file = material.file || ''
        row.md5 = material.md5 || ''
      }
    }

    function addInterruptRow() {
      createForm.value.interruptsList.push({
        trigger_type: 'command',
        ad_id: '',
        priority: 100,
        play_mode: 'loop_until_stop'
      })
    }

    function removeInterruptRow(idx) {
      createForm.value.interruptsList.splice(idx, 1)
    }

    function removeDevice(dev) {
      const idx = createForm.value.devicesSelected.indexOf(dev)
      if (idx > -1) {
        createForm.value.devicesSelected.splice(idx, 1)
      }
    }

    function selectFilteredDevices() {
      const current = createForm.value.devicesSelected
      const merged = new Set([...current, ...filteredDeviceList.value])
      createForm.value.devicesSelected = Array.from(merged)
    }

    function clearSelectedDevices() {
      createForm.value.devicesSelected = []
    }

    function validateAds() {
      adErrors.value = []

      if (createForm.value.deliveryMode === 'random') {
        if (!materials.value.length) {
          adErrors.value.push('素材库为空，无法使用随机播放')
        }
        return
      }

      const ads = createForm.value.adsList

      if (!ads.length) {
        adErrors.value.push('素材列表不能为空')
        return
      }

      ads.forEach((ad, idx) => {
        if (!ad.adId) {
          adErrors.value.push(`第 ${idx + 1} 行：请选择广告`)
        }
        // 关键校验：优先级、时段
        if (!ad.priority || ad.priority < 1 || ad.priority > 100) {
          adErrors.value.push(`第 ${idx + 1} 行：优先级必须是 1-100`)
        }
        if (!ad.slots || ad.slots.length === 0) {
          adErrors.value.push(`第 ${idx + 1} 行：至少选择一个时段`)
        }
        if (ad.slots && ad.slots.includes('*') && ad.slots.length > 1) {
          adErrors.value.push(`第 ${idx + 1} 行：'*' 不能与其他时段混用`)
        }
      })

      // 检查 ID 重复
      const ids = ads.map(a => a.adId).filter(Boolean)
      const duplicates = ids.filter((id, idx) => ids.indexOf(id) !== idx)
      if (duplicates.length) {
        adErrors.value.push(`广告 ID 重复: ${[...new Set(duplicates)].join(', ')}`)
      }
    }

    function validateInterrupts() {
      interruptErrors.value = []
      const interrupts = createForm.value.interruptsList

      // 只有在有中断策略时才进行验证
      if (!interrupts.length) return

      interrupts.forEach((item, idx) => {
        // 关键校验：优先级
        if (!item.priority || item.priority < 1) {
          interruptErrors.value.push(`第 ${idx + 1} 行：优先级必须 ≥ 1`)
        }
      })
    }

    async function submitCreate() {
      // 验证
      validateAds()
      validateInterrupts()

      if (adErrors.value.length) {
        ElMessage.error(`素材验证失败，请检查表格`)
        return
      }

      if (!createForm.value.devicesSelected.length) {
        ElMessage.error('请至少选择一个目标设备')
        return
      }

      if (!createForm.value.name.trim()) {
        ElMessage.error('策略名不能为空')
        return
      }

      if (isEditMode.value && !createForm.value.creator_id.trim()) {
        ElMessage.error('修改者不能为空')
        return
      }

      creating.value = true
      try {
        // 构建 ads_list
        const adsList = createForm.value.deliveryMode === 'random'
          ? materials.value.map(mat => ({
            id: mat.material_id,
            file: mat.file || mat.file_name || '',
            md5: mat.md5 || '',
            priority: 10,
            slots: ['*']
          }))
          : createForm.value.adsList.map(row => ({
            id: row.adId,
            file: row.file,
            md5: row.md5,
            priority: Number(row.priority),
            slots: row.slots || []
          }))

        // 构建 interrupts
        const interrupts = createForm.value.interruptsList.map(row => ({
          trigger_type: row.trigger_type,
          ad_id: row.ad_id,
          priority: Number(row.priority),
          play_mode: row.play_mode
        }))

        const payload = {
          ads_list: adsList,
          devices_list: createForm.value.devicesSelected,
          time_rules: {
            name: createForm.value.name,
            creator_id: createForm.value.creator_id,
            interrupts,
          },
          download_base_url: createForm.value.download_base_url,
        }

        if (isEditMode.value) {
          await campaignApi.updateCampaignStrategy(editingCampaignId.value, payload)
          ElMessage.success(`修改成功: ${editingCampaignId.value}`)
        } else {
          const res = await campaignApi.createCampaignStrategy(payload)
          ElMessage.success(`创建成功: ${res.campaign_id}`)
        }

        createVisible.value = false
        await fetchCampaigns()
      } catch (e) {
        const detail = e?.response?.data?.detail
        const errMsg = typeof detail === 'string' ? detail : (detail?.message || (isEditMode.value ? '修改策略失败' : '创建策略失败'))
        ElMessage.error(errMsg)
      } finally {
        creating.value = false
      }
    }

    async function loadDevicesAndMaterials() {
      try {
        // 加载所有设备
        const resDevices = await campaignApi.listDevices({ limit: 1000, offset: 0 })
        allDevices.value = resDevices?.items?.map(d => d.device_id) || ['ELEV_001', 'ELEV_002', 'ELEV_003']
      } catch (_e) {
        allDevices.value = ['ELEV_001', 'ELEV_002', 'ELEV_003']
      }

      try {
        // 加载所有素材
        const resMaterials = await materialsApi.listMaterials({ limit: 1000, offset: 0 })
        materials.value = resMaterials?.items || []
      } catch (_e) {
        materials.value = []
      }
    }

    onMounted(async () => {
      await fetchCampaigns()
      await loadDevicesAndMaterials()
    })

    return {
      campaigns,
      loading,
      keyword,
      filteredCampaigns,
      summary,
      detailVisible,
      detailTab,
      detailCampaign,
      detailScheduleConfig,
      detailEdgeSchedule,
      detailPlaylist,
      detailDevices,
      edgeGlobal,
      edgeTimeSlots,
      edgeInterrupts,
      logsVisible,
      versionsVisible,
      activeCampaignId,
      publishLogs,
      versionList,
      rollbackPublishNow,
      createVisible,
      isEditMode,
      editingCampaignId,
      editingVersion,
      creating,
      createForm,
      materials,
      allDevices,
      filteredDeviceList,
      deviceSearchKeyword,
      adErrors,
      interruptErrors,
      fetchCampaigns,
      openDetail,
      openEditDialog,
      deleteCampaignRow,
      publishNow,
      openLogs,
      refreshLogs,
      retryFailedDevices,
      openVersions,
      refreshVersions,
      rollbackVersion,
      showVersionDetail,
      openCreateDialog,
      submitCreate,
      formatDate,
      formatCampaignStatus,
      pretty,
      versionPlaylistCount,
      versionInterruptCount,
      versionDownloadBaseUrl,
      materialNameById,
      materialAdvertiserById,
      deviceCount,
      addAdRow,
      removeAdRow,
      onAdSelect,
      addInterruptRow,
      removeInterruptRow,
      removeDevice,
      selectFilteredDevices,
      clearSelectedDevices,
      validateAds,
      validateInterrupts,
      resetCreateForm,
    }
  }
}
</script>

<style scoped>
.campaign-page {
  padding: 16px;
  background: radial-gradient(circle at 0% 0%, #f9f1dc, #f5f7fb 35%), linear-gradient(180deg, #fdfefe, #f3f5f8);
  min-height: calc(100vh - 56px);
}

.hero-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  padding: 18px 20px;
  border-radius: 14px;
  background: linear-gradient(120deg, #10233f, #1c3f66 45%, #2e6b74);
  color: #f4f9ff;
}

.hero-card h2 {
  margin: 0;
  font-size: 22px;
}

.hero-card p {
  margin: 8px 0 0;
  opacity: 0.9;
}

.hero-actions {
  display: flex;
  gap: 8px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.stat-card {
  border-radius: 12px;
}

.stat-label {
  color: #6a7488;
  font-size: 13px;
}

.stat-value {
  margin-top: 8px;
  font-size: 28px;
  font-weight: 700;
  color: #0f2e55;
}

.table-card {
  border-radius: 12px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.dialog-title {
  font-size: 16px;
  font-weight: 700;
  color: #17345a;
}

.section-title {
  margin: 14px 0 10px;
  color: #2b405d;
}

.tag-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.muted {
  color: #98a2b3;
}

.mini-card {
  font-size: 13px;
  color: #3b516f;
}

.json-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.json-box {
  margin: 0;
  max-height: 56vh;
  overflow: auto;
  padding: 12px;
  border-radius: 8px;
  background: #0e1a2a;
  color: #d7e7ff;
  font-size: 12px;
}

.mr8 {
  margin-right: 8px;
}

.create-form-wrapper {
  max-height: 70vh;
  overflow-y: auto;
  padding: 0 12px;
}

.form-table {
  margin-bottom: 12px;
  border-radius: 2px;
}

.form-table :deep(.el-table__header th) {
  background-color: #f5f7fa;
  font-weight: 600;
}

.device-selector {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 12px;
  max-height: 200px;
  overflow-y: auto;
  background-color: #fafbfc;
}

.device-list {
  max-height: 160px;
  overflow-y: auto;
}

.device-select-layout {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.device-select-main {
  flex: 1;
  min-width: 0;
}

.device-search-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.device-select-side {
  flex: 0 0 auto;
  padding-top: 2px;
}

@media (max-width: 960px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }

  .json-grid {
    grid-template-columns: 1fr;
  }

  .hero-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .device-select-layout {
    flex-direction: column;
  }

  .device-select-side {
    padding-top: 0;
  }
}
</style>
