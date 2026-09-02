<template>
  <v-container fluid>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-3">
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
        show-expand
        v-model:expanded="expanded"
        class="elevation-1"
        :loading="loading"
        @update:expanded="loadDetail"
      >
        <template v-slot:expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="pa-0">
              <div v-if="!detail[item.state]" class="pa-4 text-medium-emphasis">
                {{ $t("components.StateDurationsTable.Loading") }}
              </div>
              <v-table v-else density="compact" class="state-detail">
                <thead>
                  <tr>
                    <th>{{ $t("components.StateDurationsTable.Minion") }}</th>
                    <th>{{ $t("components.StateDurationsTable.Sls") }}</th>
                    <th class="text-right">{{ $t("components.StateDurationsTable.Duration") }}</th>
                    <th>{{ $t("components.StateDurationsTable.Result") }}</th>
                    <th>{{ $t("components.StateDurationsTable.Comment") }}</th>
                    <th>{{ $t("components.StateDurationsTable.When") }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in detail[item.state]" :key="row.minion + row.jid">
                    <td>
                      <router-link :to="'/minions/' + row.minion" class="text-primary">
                        {{ row.minion }}
                      </router-link>
                    </td>
                    <td>{{ row.sls }}</td>
                    <td class="text-right">{{ seconds(row.duration_ms) }}</td>
                    <td>
                      <v-chip :color="resultColor(row)" size="small" label>
                        {{ resultText(row) }}
                      </v-chip>
                    </td>
                    <td class="text-medium-emphasis">{{ row.comment }}</td>
                    <td>
                      <router-link
                        :to="'/jobs/' + row.jid + '/' + row.minion"
                        class="text-primary"
                      >
                        {{ new Date(row.when).toLocaleString("en-GB") }}
                      </router-link>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </td>
          </tr>
        </template>
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
      expanded: [],
      detail: {},
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
      this.detail = {}
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
    // Fetched per state on expand rather than up front: the fleet aggregate
    // is one pass over the highstates, and doing that per row would repeat it.
    loadDetail(expanded) {
      const list = expanded || []
      list.forEach((state) => {
        if (this.detail[state]) {
          return
        }
        this.$http
          .get("api/states/durations/", {
            params: { days: this.days, state: state, id: this.minion },
          })
          .then((response) => {
            this.detail = { ...this.detail, [state]: response.data.minions }
          })
          .catch(() => {
            this.detail = { ...this.detail, [state]: [] }
          })
      })
    },
    resultColor(row) {
      if (row.result === false) return "error"
      return row.changed ? "warning" : "success"
    },
    resultText(row) {
      if (row.result === false) return this.$t("components.StateDurationsTable.Failed")
      return row.changed
        ? this.$t("components.StateDurationsTable.Changed")
        : this.$t("components.StateDurationsTable.Clean")
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

.state-detail {
  background: rgba(128, 128, 128, 0.06);
}
</style>
