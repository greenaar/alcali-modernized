<template>
  <v-container fluid>
    <v-card>
      <v-card-title>
        {{ $t("components.SilentMinionsCard.Title") }}
        <v-spacer></v-spacer>
        <v-select
          :items="windows"
          item-title="text"
          item-value="value"
          v-model="days"
          @update:model-value="loadData"
          density="compact"
          hide-details
          variant="plain"
          class="window"
        ></v-select>
      </v-card-title>
      <v-card-text v-if="loading">
        <v-progress-linear indeterminate></v-progress-linear>
      </v-card-text>
      <template v-else>
        <v-card-text v-if="silent.length === 0" class="text-medium-emphasis">
          {{ $t("components.SilentMinionsCard.AllReporting", [accepted]) }}
        </v-card-text>
        <template v-else>
          <v-card-text class="pb-0">
            {{ $t("components.SilentMinionsCard.Summary", [silent.length, accepted]) }}
          </v-card-text>
          <v-table density="compact">
            <tbody>
              <tr v-for="row in silent" :key="row.minion_id">
                <td>
                  <v-btn
                    v-if="row.inventoried"
                    variant="text"
                    size="small"
                    class="text-none px-1"
                    :to="'/minions/' + row.minion_id"
                    >{{ row.minion_id }}</v-btn
                  >
                  <span v-else class="pl-1">{{ row.minion_id }}</span>
                </td>
                <td class="text-right">
                  <v-chip :color="row.last_job ? 'orange' : 'red'" size="small" label>
                    {{
                      row.last_job
                        ? $t("components.SilentMinionsCard.DaysAgo", [row.days])
                        : $t("components.SilentMinionsCard.NeverReturned")
                    }}
                  </v-chip>
                </td>
              </tr>
            </tbody>
          </v-table>
        </template>
      </template>
    </v-card>
  </v-container>
</template>

<script>
export default {
  name: "SilentMinionsCard",
  data() {
    return {
      // A minion that stops answering leaves no row in salt_returns, so it
      // shows up nowhere else in the UI. The accepted keys are the roster.
      silent: [],
      accepted: 0,
      days: 1,
      loading: true,
      windows: [
        { text: this.$t("components.SilentMinionsCard.Day"), value: 1 },
        { text: this.$t("components.SilentMinionsCard.ThreeDays"), value: 3 },
        { text: this.$t("components.SilentMinionsCard.Week"), value: 7 },
        { text: this.$t("components.SilentMinionsCard.Month"), value: 30 },
      ],
    }
  },
  mounted() {
    this.loadData()
  },
  methods: {
    loadData() {
      this.loading = true
      this.$http
        .get("api/minions/silent/", { params: { days: this.days } })
        .then((response) => {
          this.silent = response.data.silent
          this.accepted = response.data.accepted
          this.loading = false
        })
        .catch(() => {
          this.loading = false
        })
    },
  },
}
</script>

<style scoped>
.window {
  max-width: 130px;
}
</style>
