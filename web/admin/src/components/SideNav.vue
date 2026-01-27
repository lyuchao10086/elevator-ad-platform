<template>
  <aside class="sidenav">
    <div class="logo">菜单栏</div>
    <el-menu default-active="1" class="el-menu-vertical-demo" router>
      <el-menu-item index="/">控制面板</el-menu-item>
      <el-menu-item index="/devices">设备</el-menu-item>
      <el-menu-item index="/materials">广告素材</el-menu-item>
      <el-menu-item index="/campaigns">投放策略</el-menu-item>
      <el-menu-item index="/commands">指令中心</el-menu-item>
    </el-menu>
  </aside>
</template>

<script>
export default {}
</script>

<style scoped>
.sidenav{width:220px;background:#001529;color:#fff;padding:16px}
.logo{color:#fff;font-weight:600;margin-bottom:12px}
</style>
