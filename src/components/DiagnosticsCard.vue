<template>
  <v-container fluid>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-3">
        {{ $t("components.DiagnosticsCard.Title") }}
        <v-chip v-if="status" :color="statusColor(status)">
          {{ $t(`components.DiagnosticsCard.status_${status}`) }}
        </v-chip>
        <v-spacer></v-spacer>
        <v-btn variant="tonal" :loading="loading" @click="run">
          {{ $t("components.DiagnosticsCard.Run") }}
        </v-btn>
      </v-card-title>
      <v-card-text>
        <p class="text-caption text-medium-emphasis mt-n2">
          {{ $t("components.DiagnosticsCard.Hint") }}
        </p>

        <v-alert v-if="error" type="error" class="mb-0">{{ error }}</v-alert>

        <v-list v-else-if="checks.length" lines="two">
          <v-list-item v-for="check in checks" :key="check.key">
            <template v-slot:prepend>
              <v-icon :color="statusColor(check.status)">
                {{ statusIcon(check.status) }}
              </v-icon>
            </template>
            <v-list-item-title>{{ check.label }}</v-list-item-title>
            <v-list-item-subtitle class="text-wrap">
              {{ check.detail }}
            </v-list-item-subtitle>
            <v-alert
              v-if="check.hint"
              :type="check.status === 'fail' ? 'error' : 'info'"
              density="compact"
              class="mt-2 text-body-2"
            >
              {{ check.hint }}
            </v-alert>
          </v-list-item>
        </v-list>

        <p v-else-if="!loading" class="text-medium-emphasis mb-0">
          {{ $t("components.DiagnosticsCard.Idle") }}
        </p>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script>
export default {
  name: "DiagnosticsCard",
  data() {
    return {
      checks: [],
      status: null,
      error: null,
      loading: false,
    }
  },
  mounted() {
    this.run()
  },
  methods: {
    statusColor(status) {
      return (
        { ok: "success", warn: "warning", fail: "error" }[status] || "grey"
      )
    },
    statusIcon(status) {
      return (
        {
          ok: "check_circle",
          warn: "warning",
          fail: "error",
        }[status] || "help"
      )
    },
    run() {
      this.loading = true
      this.error = null
      this.$http
        .get("api/diagnostics/")
        .then((response) => {
          this.checks = response.data.checks
          this.status = response.data.status
        })
        .catch((error) => {
          let data = error.response && error.response.data
          this.error = (data && (data.error || data.detail)) || String(error)
        })
        .then(() => {
          this.loading = false
        })
    },
  },
}
</script>
