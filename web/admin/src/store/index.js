import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', {
  state: () => ({ token: null, user: null }),
  actions: {
    setToken(t) { this.token = t },
    setUser(u) { this.user = u }
  }
})
