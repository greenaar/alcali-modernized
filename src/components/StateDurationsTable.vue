<template>
  <v-container fluid>
    <v-card>
      <v-card-title>
        {{ $t("components.StateDurationsTable.Title") }}
        <span class="text-caption text-medium-emphasis ml-3">
          {{ $t("components.StateDurationsTable.Subtitle", [highstates, days]) }}
        </span>
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
          class="window mr-4"
        ></v-select>
        <v-text-field
          class="search"
          v-model="search"
          append-icon="search"
          :label="$t('common.Search')"
          single-line
          hide-details
        ></v-text-field>
      </v-card-title>
      <legacy-data-table
        :headers="headers"
        :items="states"
        :search="search"
        item-value="state"
        sort-by="total_ms"
        sort-desc
        class="elevation-1"
        :loading="loading"
      >
        <template v-slot:item.total_ms="{ item }">
          {{ seconds(item.total_ms) }}
        </template>
        <template v-slot:item.mean_ms="{ item }">
          {{ seconds(item.mean_ms) }}
        </template>
        <template v-slot:item.max_ms="{ item }">
          {{ seconds(item.max_ms) }}
        </template>
        <template v-slot:item.change_rate="{ item }">
          <v-chip
            :color="driftColor(item.change_rate)"
            size="small"
            label
          >
            {{ Math.round(item.change_rate * 100) }}%
          </v-chip>
        </template>
        <template v-slot:item.failed="{ item }">
          <v-chip v-if="item.failed > 0" color="red" size="small" label>
            {{ item.failed }}
          </v-chip>
          <span v-else>0</span>
        </template>
      </legacy-data-table>
    </v-card>
  </v-container>
</template>

<script>
export default {
  name: "StateDurationsTable",
  props: ["minion"],
  data() {
    return {
      search: "",
      states: [],
      highstates: 0,
      days: 7,
      loading: true,
      windows: [
        { text: this.$t("components.StateDurationsTable.Day"), value: 1 },
        { text: this.$t("components.StateDurationsTable.Week"), value: 7 },
        { text: this.$t("components.StateDurationsTable.Month"), value: 30 },
      ],
      headers: [
        { text: this.$t("components.StateDurationsTable.State"), value: "state" },
        { text: this.$t("components.StateDurationsTable.Sls"), value: "sls" },
        { text: this.$t("components.StateDurationsTable.Total"), value: "total_ms" },
        { text: this.$t("components.StateDurationsTable.Mean"), value: "mean_ms" },
        { text: this.$t("components.StateDurationsTable.Slowest"), value: "max_ms" },
        { text: this.$t("components.StateDurationsTable.Runs"), value: "runs" },
        { text: this.$t("components.StateDurationsTable.Minions"), value: "minions" },
        { text: this.$t("components.StateDurationsTable.Changing"), value: "change_rate" },
        { text: this.$t("components.StateDurationsTable.Failed"), value: "failed" },
      ],
    }
  },
  mounted() {
    this.loadData()
  },
  methods: {
    loadData() {
      this.loading = true
      let params = { days: this.days }
      if (this.minion) {
        params.id = this.minion
      }
      this.$http
        .get("api/states/durations/", { params: params })
        .then((response) => {
          this.states = response.data.states
          this.highstates = response.data.highstates
          this.loading = false
        })
        .catch(() => {
          this.loading = false
        })
    },
    seconds(ms) {
      if (ms >= 1000) {
        return (ms / 1000).toFixed(1) + "s"
      }
      return Math.round(ms) + "ms"
    },
    // A state that reports changes on most runs is being re-applied every
    // time rather than converging.
    driftColor(rate) {
      if (rate >= 0.9) return "red"
      if (rate >= 0.25) return "orange"
      return "green"
    },
  },
}
</script>

<style scoped>
.window {
  max-width: 120px;
}
</style>
