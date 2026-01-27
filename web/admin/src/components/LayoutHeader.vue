<template>
  <header class="layout-header">
    <div class="left">
      <el-input placeholder="搜索（设备、素材）" v-model="q" size="small" style="width:320px" @keyup.enter="onSearch"/>
    </div>
    <div class="right">
      <el-button type="warning" size="small" @click="$router.push('/commands')">确定</el-button>
    </div>
  </header>
</template>

<script>
export default { data(){return {q:''}}, methods:{ onSearch(){ this.$emit('search', this.q) } } }
</script>

<style scoped>
.layout-header{display:flex;justify-content:space-between;align-items:center;padding:12px 20px;border-bottom:1px solid #eee;background:#fff}
</style>
