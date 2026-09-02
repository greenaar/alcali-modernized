import { createStore } from "vuex"
import axios from "axios"
import defaultSettings, { mergeSettings } from "./settings-defaults"

export default createStore({
  state: {
    username: localStorage.getItem("username") || "",
    email: localStorage.getItem("email") || "",
    id: localStorage.getItem("id") || "",
    access: localStorage.getItem("access") || "",
    refresh: localStorage.getItem("refresh") || "",
    is_staff: localStorage.getItem("is_staff") === "true",
    ws_status: false,
    settings: defaultSettings(),
  },
  mutations: {
    auth_success(state, data) {
      Object.keys(data).forEach(key => {
        state[key] = data[key]
      })
    },
    logout(state) {
      state.access = ""
    },
    updateWs(state, connected = true) {
      // Takes a value now: the stream can drop, and an indicator that only
      // ever moves one way cannot report that.
      state.ws_status = connected !== false
    },
    setSettings(state, settings) {
      state.settings = mergeSettings(defaultSettings(), settings)
    },
    updateSettings(state) {
      axios.patch(`api/userssettings/${state.id}/`, { settings: state.settings }).then(() => {
      }).catch((err) => {
        console.log("update settings failed:", err)
      })
    },
  },
  getters: {
    isLoggedIn: state => !!state.access,
    user_id: state => state.id,
    isStaff: state => state.is_staff,
    settings: state => state.settings,
  },
  actions: {
    updateWs({ commit }, connected = true) {
      commit("updateWs", connected)
    },
    toggleTheme({ commit }) {
      commit("toggleTheme")
    },
    fetchSettings(context) {
      axios.get(`api/userssettings/${context.getters.user_id}/`).then(response => {
        context.commit("setSettings", response.data.settings)
      }).catch(err => {
        console.log(err)
      })
    },
    login({ commit }, user_data) {
      return new Promise((resolve, reject) => {
        axios({ url: "/api/token/", data: user_data, method: "POST" })
          .then(resp => {
            Object.keys(resp.data).forEach(key => {
              localStorage.setItem(key, resp.data[key])
            })
            axios.defaults.headers.common.Authorization = `Bearer ${resp.data.access}`
            commit("auth_success", resp.data)
            resolve(resp)
          })
          .catch(err => {
            localStorage.clear()
            reject(err)
          })
      })
    },
    oauthlogin({ commit }, user_data) {
      return new Promise((resolve, reject) => {
        axios({ url: "/api/social/login/", data: user_data, method: "POST" })
          .then(resp => {
            // rename token to access
            delete Object.assign(resp.data, {["access"]: resp.data["token"] })["token"]
            Object.keys(resp.data).forEach(key => {
              localStorage.setItem(key, resp.data[key])
            })
            axios.defaults.headers.common.Authorization = `Bearer ${resp.data.access}`
            commit("auth_success", resp.data)
            resolve(resp)
          })
          .catch(err => {
            localStorage.clear()
            reject(err)
          })
      })
    },
    logout({ commit }) {
      return new Promise((resolve) => {
        commit("logout")
        localStorage.clear()
        delete axios.defaults.headers.common["Authorization"]
        resolve()
      })
    },

  },
})
