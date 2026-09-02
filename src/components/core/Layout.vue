<template>
  <v-app>
    <v-navigation-drawer
      v-model="settings.Layout.drawer"
      :rail="settings.Layout.mini"
      :expand-on-hover="settings.Layout.mini"
      color="surface"
      border="0"
    >
      <!-- Vuetify 3's own list item: prepend-icon and title lay the icon
           beside the label. The v-list-item-content/-action wrappers this
           used to nest were Vue 2 components, shimmed here as plain divs,
           and a div is block level - which is why every icon sat above its
           label rather than next to it. -->
      <v-list class="py-2">
        <v-list-item
          :prepend-avatar="undefined"
          :title="username"
          :subtitle="email"
          class="drawer-account"
        >
          <template v-slot:prepend>
            <v-avatar color="primary" size="36">
              <v-icon size="20">person</v-icon>
            </v-avatar>
          </template>
        </v-list-item>
      </v-list>
      <v-divider></v-divider>
      <v-list density="compact" nav class="py-2">
        <v-list-item
          v-for="route in routes"
          :key="route.name"
          :to="route.path"
          :prepend-icon="route.icon"
          :title="$t(route.name)"
          color="primary"
          rounded="lg"
        ></v-list-item>
      </v-list>
      <v-divider></v-divider>
      <v-list density="compact" nav class="py-2">
        <v-list-item
          to="/users"
          prepend-icon="group"
          :title="$t('components.core.Layout.Users')"
          color="primary"
          rounded="lg"
        ></v-list-item>
        <v-list-item
          to="/settings"
          prepend-icon="settings"
          :title="$t('components.core.Layout.Settings')"
          color="primary"
          rounded="lg"
        ></v-list-item>
      </v-list>
      <template v-slot:append>
        <v-divider></v-divider>
        <v-list density="compact" nav class="py-2">
          <v-list-item
            @click.stop="updateDomAndSettings('mini')"
            :prepend-icon="settings.Layout.mini ? 'chevron_right' : 'chevron_left'"
            :title="$t('components.core.Layout.Collapse')"
            rounded="lg"
          ></v-list-item>
        </v-list>
      </template>
    </v-navigation-drawer>
    <!-- Was hard-coded black with `dark`, so it ignored the theme entirely
         and stayed the same slab in both. -->
    <v-app-bar color="surface" flat border="0 0 thin 0" height="60">
      <v-app-bar-nav-icon @click.stop="updateDomAndSettings('drawer')"></v-app-bar-nav-icon>
      <v-toolbar-title class="font-weight-bold text-primary app-title">ALCALI</v-toolbar-title>
      <v-spacer></v-spacer>
      <v-expand-transition>
        <v-text-field
          v-show="expand_search"
          class="mx-auto search"
          density="compact"
          hide-details
          variant="solo-filled"
          flat
          prepend-inner-icon="search"
          :label="$t('components.core.Layout.Search')"
          v-model="searchInput"
          @keyup.enter="searchBar"
        ></v-text-field>
      </v-expand-transition>
      <v-btn icon variant="text" @click="expand_search = !expand_search" class="mr-1">
        <v-icon>search</v-icon>
      </v-btn>
      <v-menu v-model="notif_menu" bottom left offset-y offset-x>
        <template v-slot:activator="{ props }">
          <v-badge :color="notif_nb > 0 ? 'primary' : 'transparent'" overlap>
            <template v-slot:badge>
              <span v-if="notif_nb > 0">{{ notif_nb }}</span>
            </template>
            <v-icon v-bind="props" @click="notif_nb = 0">notifications</v-icon>
          </v-badge>
        </template>
        <v-card min-width="500px" max-width="500px">
          <v-list max-height="700px" lines="two">
            <v-list-item
              v-if="messages.length === 0"
              :subtitle="$t('components.core.Layout.NoNotifications')"
            ></v-list-item>
            <v-list-item
              v-for="(item, i) in messages"
              :key="i"
              :to="item.link"
              :title="item.text"
              :subtitle="item.tag"
            >
              <template v-slot:prepend>
                <v-avatar :color="item.color" size="32">
                  <v-icon size="18">{{ item.icon }}</v-icon>
                </v-avatar>
              </template>
            </v-list-item>
          </v-list>
          <v-card-actions v-show="messages.length > 0">
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="messages = []">{{ $t("components.core.Layout.Clear") }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-menu>
      <v-menu bottom left offset-y offset-x close-on-click>
        <template v-slot:activator="{ props }">
          <v-btn v-bind="props" icon variant="text">
            <v-icon>more_vert</v-icon>
          </v-btn>
        </template>
        <v-list>
          <v-list-item @click="updateDomAndSettings('dark')">
            <v-list-item-title>{{ $t("components.core.Layout.ToggleTheme") }}</v-list-item-title>
          </v-list-item>
          <v-divider></v-divider>
          <v-list-item @click="logout">
            <v-list-item-title>{{ $t("components.core.Layout.Logout") }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-app-bar>
    <v-main>
      <router-view v-slot="{ Component }">
        <v-fade-transition mode="out-in">
          <component :is="Component" :key="$route.fullPath" />
        </v-fade-transition>
      </router-view>
    </v-main>
  </v-app>
</template>

<script>
import { mapState } from "vuex"
import { EventSourcePolyfill } from "event-source-polyfill"
import helpersMixin from "../mixins/helpersMixin"

export default {
  name: "Layout",
  props: {
    source: String,
  },
  data: () => ({
    expand_search: false,
    notif_menu: false,
    searchInput: "",
    eventSource: null,
    streamBackoff: 0,
    streamTimer: null,
    messages: [],
    notif_nb: 0,
    routes: [
      {
        name: "components.core.Layout.Overview",
        path: "/",
        icon: "dashboard",
      },
      {
        name: "components.core.Layout.Minions",
        path: "/minions",
        icon: "device_hub",
      },
      {
        name: "components.core.Layout.Jobs",
        path: "/jobs",
        icon: "playlist_play",
      },
      {
        name: "components.core.Layout.Run",
        path: "/run",
        icon: "play_arrow",
      },
      {
        name: "components.core.Layout.JobTemplates",
        path: "/job_templates",
        icon: "playlist_add_check",
      },
      {
        name: "components.core.Layout.Schedules",
        path: "/schedules",
        icon: "schedule",
      },
      {
        name: "components.core.Layout.Conformity",
        path: "/conformity",
        icon: "done_all",
      },
      {
        name: "components.core.Layout.States",
        path: "/states",
        icon: "timer",
      },
      {
        name: "components.core.Layout.Keys",
        path: "/keys",
        icon: "vpn_key",
      },
      {
        name: "components.core.Layout.Events",
        path: "/events",
        icon: "playlist_add",
      },
    ],
  }),
  methods: {
    updateDomAndSettings(val) {
      this.settings.Layout[val] = !this.settings.Layout[val]
      if (val === 'dark') {
        this.applyTheme()
      }
      this.$store.commit("updateSettings")
    },
    applyTheme() {
      this.$vuetify.theme.change(this.settings.Layout.dark ? "dark" : "light")
    },
    logout: function() {
      this.$store.dispatch("logout").then(() => {
        this.$router.push("/login");
      });
    },
    searchBar() {
      if (this.searchInput !== "") {
        this.$router.push({ name: "search", query: { q: this.searchInput } });
      }
    },
    getPrefs() {
      this.$store.dispatch("fetchSettings")
    },
    toggleTheme() {
      this.$store.dispatch("toggleTheme").then(() => {
        this.applyTheme();
      });
    },
    scheduleReconnect() {
      if (this.streamTimer || this.destroyed) {
        return;
      }
      if (this.eventSource) {
        // The polyfill retries on its own otherwise, from one second.
        this.eventSource.close();
        this.eventSource = null;
      }
      // 5s, then doubling to a minute: quick enough to notice a master coming
      // back, slow enough not to be a login flood while it is down.
      this.streamBackoff = Math.min(this.streamBackoff ? this.streamBackoff * 2 : 5000, 60000);
      this.streamTimer = setTimeout(() => {
        this.streamTimer = null;
        this.saltStatus();
      }, this.streamBackoff);
    },
    saltStatus() {
      // Various Salt event tag matchers.
      let isJobEvent = helpersMixin.methods.fnmatch("salt/job/*");
      let isJobNew = helpersMixin.methods.fnmatch("salt/job/*/new");
      let isJobReturn = helpersMixin.methods.fnmatch("salt/job/*/ret/*");
      const accessToken = localStorage.getItem("access");
      let es = new EventSourcePolyfill("/api/event_stream/", {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      es.addEventListener("open", () => {
        this.streamBackoff = 0;
        this.$store.dispatch("updateWs", true);
      });
      // The endpoint answers 503 when the master cannot be reached. The
      // polyfill would then reconnect from one second, and every attempt costs
      // the server a full Salt login - so an unreachable master had every open
      // page hammering salt-api for as long as it stayed open. Take the
      // reconnection over ourselves and back off properly instead.
      es.addEventListener("error", () => {
        this.$store.dispatch("updateWs", false);
        this.scheduleReconnect();
      });
      this.eventSource = es;
      es.addEventListener(
        "message",
        (event) => {
          let data = JSON.parse(event.data);
          // Display only activated notifs.
          if (isJobNew(data.tag) && this.settings.UserSettings.notifs.published === true) {
            if (data.data.fun !== "saltutil.find_job") {
              data.type = "new";
              data.color = "green";
              data.icon = "keyboard_tab";
              data.link = "";
              let target = "";
              if (Object.prototype.hasOwnProperty.call(data.data, "tgt")) {
                target = data.data.tgt;
              } else {
                target = data.data.minions.length + " minion(s)";
              }
              data.text =
                this.$i18n.t("components.core.Layout.Job_") +
                data.data.fun +
                this.$i18n.t("components.core.Layout._published for_") +
                target;
              this.messages.unshift(data);
              if (this.messages.length > this.settings.UserSettings.max_notifs) {
                this.messages.pop();
              }
              this.notif_nb += 1;
            } else {
              let findJobJid = data.data.jid;
              this.messages.forEach((message, index) => {
                if (message.tag === findJobJid) {
                  this.messages.splice(index, 1);
                  this.notif_nb -= 1;
                }
              });
            }
          } else if (isJobReturn(data.tag) && this.settings.UserSettings.notifs.returned === true) {
            if (data.data.fun !== "saltutil.find_job") {
              data.type = "return";
              data.color = "primary";
              data.icon = "subdirectory_arrow_left";
              data.text =
                this.$i18n.t("components.core.Layout.Job_") +
                data.data.fun +
                this.$i18n.t("components.core.Layout._returned for_") +
                data.data.id;
              data.link = "/jobs/" + data.data.jid + "/" + data.data.id;
              this.messages.unshift(data);
              if (this.messages.length > this.settings.UserSettings.max_notifs) {
                this.messages.pop();
              }
              this.notif_nb += 1;
            }
          } else if (isJobEvent(data.tag) && this.settings.UserSettings.notifs.event === true) {
            data.type = "event";
            data.color = "orange";
            data.icon = "more_horiz";
            data.text = this.$i18n.t("components.core.Layout.JobEvent");
            data.link = "";
            this.messages.unshift(data);
            if (this.messages.length > this.settings.UserSettings.max_notifs) {
              this.messages.pop();
            }
            this.notif_nb += 1;
          } else if (/^\w{20}$/.test(data.tag) && this.settings.UserSettings.notifs.created === true) {
            data.type = "created";
            data.color = "secondary";
            data.icon = "add";
            data.text = this.$i18n.t("components.core.Layout.NewJobCreated");
            data.link = "";
            this.messages.unshift(data);
            if (this.messages.length > this.settings.UserSettings.max_notifs) {
              this.messages.pop();
            }
            this.notif_nb += 1;
          }
        },
        false
      );
    },
  },
  created() {
    this.getPrefs()
    this.saltStatus()
    this.applyTheme()
  },
  beforeUnmount() {
    this.destroyed = true
    clearTimeout(this.streamTimer)
    if (this.eventSource) {
      this.eventSource.close()
    }
  },
  watch: {
    // The stored preference only lands once fetchSettings resolves.
    "settings.Layout.dark"() {
      this.applyTheme()
    },
  },
  computed: {
    ...mapState({
      username: state => state.username,
      email: state => state.email,
      settings: state => state.settings,
    }),
  },
}
</script>

<style>
/* The bar and drawer share the card surface, so a hairline is what separates
   them from the content rather than a block of solid colour. */
.app-title {
  letter-spacing: 0.12em;
}

.drawer-account {
  min-height: 56px;
}

::-webkit-scrollbar-track {
  -webkit-box-shadow: inset 0 0 6px rgba(0, 0, 0, 0.3);
  border-radius: 10px;
  background-color: #f5f5f5;
}

::-webkit-scrollbar {
  width: 10px;
  background-color: #f5f5f5;
}

::-webkit-scrollbar-thumb {
  border-radius: 10px;
  -webkit-box-shadow: inset 0 0 6px rgba(0, 0, 0, 0.3);
  background-color: #555;
}

span .v-chip__content {
  white-space: nowrap;
}

.v-list {
  border-radius: 0px !important;
}

.search {
  max-width: 380px !important;
}
</style>
