import { createApp } from "vue";
import App from "./App.vue";
import LegacyDataTable from "./components/core/LegacyDataTable.vue";
import vuetify from "./plugins/vuetify";
import router from "./router";
import axios from "axios";
import store from "./store";
import { jwtDecode } from "jwt-decode";
import DOMPurify from "dompurify";
import { createI18n } from "vue-i18n";
import { languages, defaultLocale } from "./i18n/index.js";

const messages = Object.assign(languages);
const i18n = createI18n({
  legacy: true,
  // modify $i18n.locale in App component to switch locale
  // see https://tutorialedge.net/javascript/vuejs/vuejs-i18n-basics-tutorial/#changing-locale-dynamically
  // change the localization in vuetify plugin too : $vuetify.lang.current
  locale: defaultLocale,
  messages,
});

// Every call site addresses the API relatively ("api/jobs/<jid>/<id>/"), which
// the browser would otherwise resolve against the current route: on a nested
// route such as /jobs/<jid>/<id> that produces /jobs/<jid>/api/jobs/... and 404s.
// Pinning the base URL to the site root keeps those relative paths correct on
// every route, and leaves the "/api/..." call sites unchanged.
axios.defaults.baseURL = "/";

axios.defaults.xsrfCookieName = "csrftoken";
axios.defaults.xsrfHeaderName = "X-CSRFToken";
axios.defaults.headers.common["Content-Type"] =
  "application/json";

const accessToken = localStorage.getItem("access");
if (accessToken) {
  axios.defaults.headers.common.Authorization = `Bearer ${accessToken}`;
  axios.defaults.withCredentials = true;
}

/// for multiple parallel requests
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });

  failedQueue = [];
};

axios.interceptors.request.use(
  (config) => {
    const originalRequest = config;
    // before request is sent check if refresh token is about to expire.
    const refresh = window.localStorage.getItem("refresh");
    let expiring = false;
    try {
      expiring =
        !!refresh && jwtDecode(refresh).exp - Math.floor(Date.now() / 1000) < 60;
    } catch (e) {
      // An unreadable refresh token is as good as an expired one.
      expiring = !!refresh;
    }
    if (expiring) {
      // Clean up local storage and reroute to login. A request interceptor has
      // to resolve with a config or reject; returning the router's promise
      // instead handed axios a bad config and produced a malformed request.
      store.dispatch("logout").then(() => {
        router.push({ path: "/login", name: "Login" });
      });
      return Promise.reject(
        new axios.Cancel("Session expired, redirecting to login")
      );
    }
    return originalRequest;
  },
  (error) => {
    // Do something with request error
    return Promise.reject(error);
  }
);

axios.interceptors.request.use(
  (config) => {
    const originalRequest = config;
    // before request is sent check if access token is expired.
    const access = window.localStorage.getItem("access");
    if (access && jwtDecode(access).exp > Math.floor(Date.now() / 1000)) {
      return originalRequest;
      // Do not intercept on token refresh.
    } else if (
      config.url.includes("login") ||
      config.url.includes("token") ||
      config.url.includes("social")
    ) {
      return originalRequest;
    } else {
      // While we are refreshing, store other requests.
      // Add the token on resolve.
      if (isRefreshing) {
        return new Promise(function(resolve, reject) {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers["Authorization"] = "Bearer " + token;
            return originalRequest;
          })
          .catch((err) => {
            return err;
          });
      }

      //originalRequest._retry = true
      isRefreshing = true;

      const refreshToken = window.localStorage.getItem("refresh");
      return new Promise(function(resolve, reject) {
        axios
          .post("/api/token/refresh/", { refresh: refreshToken })
          .then(({ data }) => {
            window.localStorage.setItem("access", data.access);
            axios.defaults.headers.common["Authorization"] =
              "Bearer " + data.access;
            originalRequest.headers["Authorization"] = "Bearer " + data.access;
            processQueue(null, data.access);
            resolve(originalRequest);
          })
          .catch((err) => {
            processQueue(err, null);
            reject(err);
          })
          .then(() => {
            isRefreshing = false;
          });
      });
    }
  },
  (error) => {
    // Do something with request error
    return Promise.reject(error);
  }
);

const toast = (message, color = "info") => {
  window.dispatchEvent(new CustomEvent("alcali-toast", { detail: { message, color } }));
};
toast.error = (message) => toast(message, "error");

const app = createApp(App);
app.component("LegacyDataTable", LegacyDataTable);
app.config.globalProperties.$http = axios;
app.config.globalProperties.$sanitize = (html) => DOMPurify.sanitize(html);
app.config.globalProperties.$toast = toast;
app.use(i18n);
app.use(vuetify);
app.use(router);
app.use(store);
app.mount("#app");
