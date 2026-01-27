<template>
  <div class="app-layout">
    <SideNav />
    <div class="main-area">
      <LayoutHeader />
      <router-view />
    </div>
  </div>
</template>

<script>
import SideNav from './components/SideNav.vue'
import LayoutHeader from './components/LayoutHeader.vue'
export default {
  components: { SideNav, LayoutHeader }
}
</script>

<style>
.app-layout{display:flex;height:100vh}
.main-area{flex:1;display:flex;flex-direction:column}
</style>
