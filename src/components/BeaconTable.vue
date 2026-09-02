<template>
  <v-container fluid>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-3">
        {{ $t("components.BeaconTable.Title") }}
        <span class="text-caption text-medium-emphasis">
          {{ $t("components.BeaconTable.Subtitle") }}
        </span>
        <v-spacer></v-spacer>
        <v-text-field
          v-model="search"
          :label="$t('components.BeaconTable.Search')"
          hide-details
          density="compact"
          style="max-width: 260px"
        ></v-text-field>
        <v-btn variant="tonal" :loading="refreshing" @click="refresh">
          {{ $t("components.BeaconTable.Refresh") }}
        </v-btn>
      </v-card-title>
      <v-card-text>
        <legacy-data-table
          :headers="headers"
          :items="beacons"
          :search="search"
          :loading="loading"
          class="elevation-1"
        >
          <template v-slot:item.enabled="{ item }">
            <v-chip :color="item.enabled ? 'success' : 'grey'">
              {{
                item.enabled
                  ? $t("components.BeaconTable.Enabled")
                  : $t("components.BeaconTable.Disabled")
              }}
            </v-chip>
          </template>
          <template v-slot:item.config="{ item }">
            <code class="text-caption">{{ summarise(item.config) }}</code>
          </template>
          <template v-slot:item.action="{ item }">
            <div class="d-flex flex-nowrap justify-end ga-1">
              <v-btn
                size="small"
                variant="tonal"
                :color="item.enabled ? 'warning' : 'success'"
                @click="manage(item, item.enabled ? 'disable' : 'enable')"
              >
                {{
                  item.enabled
                    ? $t("components.BeaconTable.Disable")
                    : $t("components.BeaconTable.Enable")
                }}
              </v-btn>
              <v-btn size="small" variant="text" color="error"
                     @click="ask(item)">
                {{ $t("components.BeaconTable.Delete") }}
              </v-btn>
            </div>
          </template>
        </legacy-data-table>
        <p v-if="!loading && !beacons.length" class="text-medium-emphasis mt-3 mb-0">
          {{ $t("components.BeaconTable.Empty") }}
        </p>
      </v-card-text>
    </v-card>

    <v-dialog v-model="confirm" width="520">
      <v-card v-if="pending">
        <v-card-title class="text-error">
          {{ $t("components.BeaconTable.ConfirmTitle") }}
        </v-card-title>
        <v-card-text>
          {{
            $t("components.BeaconTable.ConfirmBody", [
              pending.name,
              pending.minion,
            ])
          }}
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="confirm = false">
            {{ $t("components.BeaconTable.Cancel") }}
          </v-btn>
          <v-btn color="error" :loading="working"
                 @click="manage(pending, 'delete')">
            {{ $t("components.BeaconTable.Delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
export default {
  name: "BeaconTable",
  data() {
    return {
      beacons: [],
      search: "",
      loading: true,
      refreshing: false,
      working: false,
      confirm: false,
      pending: null,
    }
  },
  computed: {
    headers() {
      return [
        { text: this.$t("components.BeaconTable.Minion"), value: "minion" },
        { text: this.$t("components.BeaconTable.Name"), value: "name" },
        { text: this.$t("components.BeaconTable.State"), value: "enabled" },
        { text: this.$t("components.BeaconTable.Config"), value: "config" },
        {
          text: this.$t("components.BeaconTable.Actions"),
          value: "action",
          sortable: false,
          align: "end",
        },
      ]
    },
  },
  mounted() {
    this.load()
  },
  methods: {
    summarise(config) {
      // The stored config is whatever beacons.list gave, which is a list of
      // single-key mappings. Showing the keys is more use in a table than the
      // raw JSON, which is often several lines.
      try {
        let parsed = JSON.parse(config)
        if (!Array.isArray(parsed)) parsed = [parsed]
        let keys = []
        parsed.forEach((entry) => {
          if (entry && typeof entry === "object") {
            Object.keys(entry).forEach((k) => {
              if (k !== "enabled") keys.push(k)
            })
          }
        })
        return keys.join(", ") || "-"
      } catch (e) {
        return config
      }
    },
    load() {
      this.loading = true
      this.$http
        .get("api/beacons/")
        .then((response) => {
          this.beacons = response.data
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
        .then(() => {
          this.loading = false
        })
    },
    refresh() {
      this.refreshing = true
      this.$http
        .post("api/beacons/refresh/", {})
        .then((response) => {
          if (response.data.no_minions_replied) {
            this.$toast.error(this.$i18n.t("components.BeaconTable.NoReply"))
          } else {
            this.$toast(
              this.$i18n.t("components.BeaconTable.Refreshed", [
                response.data.minions,
              ])
            )
          }
          this.load()
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
        .then(() => {
          this.refreshing = false
        })
    },
    ask(beacon) {
      this.pending = beacon
      this.confirm = true
    },
    manage(beacon, action) {
      this.working = true
      this.$http
        .post("api/beacons/manage/", {
          action: action,
          minion: beacon.minion,
          name: beacon.name,
        })
        .then(() => {
          this.confirm = false
          this.load()
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
        .then(() => {
          this.working = false
        })
    },
    errorText(error) {
      let data = error.response && error.response.data
      return (data && (data.error || data.detail)) || String(error)
    },
  },
}
</script>
