<template>
  <v-container fluid>
    <v-card :elevation="minion == null ? 2 : 0">
      <v-card-title class="d-flex align-center flex-wrap ga-4 py-4">
        <span>{{ $t("components.JobsChartCard.Stats") }}</span>
        <v-spacer></v-spacer>
        <v-select
          :items="filters"
          item-title="text"
          item-value="value"
          :label="$t('components.JobsChartCard.Filter')"
          v-model="settings.Home.JobsChartCard.filter"
          @update:model-value="updateSettings"
          density="compact"
          hide-details
          class="chart-control"
        ></v-select>
        <v-select
          :items="periods"
          item-title="text"
          item-value="value"
          :label="$t('components.JobsChartCard.Period')"
          v-model="settings.Home.JobsChartCard.period"
          @update:model-value="updateSettings"
          density="compact"
          hide-details
          class="chart-control"
        ></v-select>
      </v-card-title>
      <div class="px-4 pb-4">
        <canvas ref="chart"></canvas>
      </div>
    </v-card>
  </v-container>
</template>

<script>
import { Chart, registerables } from "chart.js";
import gradientLinePlugin from "../assets/js/utils/chart-line-gradient";
import { mapState } from "vuex"

Chart.register(...registerables);

export default {
  name: "JobsChartCard",
  props: ["minion"],
  data() {
    return {
      filters: [
        { text: this.$i18n.t("components.JobsChartCard.All"), value: "all" },
        {
          text: this.$i18n.t("components.JobsChartCard.Highstate"),
          value: "highstate",
        },
        {
          text: this.$i18n.t("components.JobsChartCard.Other"),
          value: "other",
        },
      ],
      periods: [
        { text: this.$i18n.t("components.JobsChartCard.Week"), value: 7 },
        { text: this.$i18n.t("components.JobsChartCard.TwoWeeks"), value: 14 },
        { text: this.$i18n.t("components.JobsChartCard.Month"), value: 30 },
        {
          text: this.$i18n.t("components.JobsChartCard.Year"),
          value: 365,
        },
      ],
      jobchart: null,
      selectedFilter: null,
      selectedPeriod: null,
      labels: null,
      chart_data: [],
    };
  },
  computed: {
    ...mapState({
      settings: state => state.settings,
    }),
  },
  mounted() {
    this.createChart();
  },
  methods: {
    updateSettings() {
      this.$store.commit("updateSettings")
      this.loadData()
    },
    loadData() {
      let params = { params: { fun: this.settings.Home.JobsChartCard.filter, period: this.settings.Home.JobsChartCard.period } }
      if (this.minion) {
        params.params.id = this.minion;
      }
      this.$http.get("api/jobs/graph", params).then((response) => {
        this.jobchart.data.labels = response.data.labels;
        this.jobchart.data.datasets[0].data = response.data.series[0];
        this.jobchart.data.datasets[1].data = response.data.series[1];
        this.jobchart.update();
      });
    },
    createChart() {
      let params = { params: { fun: this.settings.Home.JobsChartCard.filter, period: this.settings.Home.JobsChartCard.period } }
      if (this.minion) {
        params.params.id = this.minion;
      }
      if (this.jobchart != null) {
        this.jobchart.destroy();
      }
      this.$http.get("api/jobs/graph", params).then((response) => {
        this.labels = response.data.labels;
        this.chart_data[0] = response.data.series[0];
        this.chart_data[1] = response.data.series[1];
        this.$refs.chart.height = 60;
        this.jobchart = new Chart(this.$refs.chart, {
          type: "line",
          data: {
            labels: this.labels,
            datasets: [
              {
                tension: 0.1,
                pointRadius: 1,
                data: this.chart_data[0], // fake data before update(needed for plugin).
                fill: false,
                colorStart: "rgba(0, 173, 238, 1.0)",
                colorEnd: "rgba(231, 18, 143, 1.0)",
              },
              {
                tension: 0.1,
                pointRadius: 1,
                data: this.chart_data[1],
                fill: false,
                colorStart: "rgba(255, 255, 255, 1.0)",
                colorEnd: "rgba(255, 0, 0, 1.0)",
              },
            ],
          },
          options: {
            linearGradientLine: true,
            plugins: {
              legend: {
                display: false,
              },
            },
            scales: {
              x: {
                grid: {
                  display: true,
                },
              },
              y: {
                beginAtZero: true,
                grid: {
                  display: true,
                },
                ticks: {
                  autoSkip: true,
                  maxTicksLimit: 6,
                },
              },
            },
            responsive: true,
          },
          plugins: [gradientLinePlugin],
        });
      });
    },
  },
};
</script>

<style scoped>
.chart-control {
  max-width: 200px;
}
</style>
