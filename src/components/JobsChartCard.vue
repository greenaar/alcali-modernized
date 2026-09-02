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
        <canvas ref="chart" class="jobs-chart"></canvas>
      </div>
    </v-card>
  </v-container>
</template>

<script>
import { markRaw } from "vue";
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
    };
  },
  computed: {
    ...mapState({
      settings: state => state.settings,
    }),
    filter() {
      return this.settings.Home.JobsChartCard.filter
    },
    period() {
      return this.settings.Home.JobsChartCard.period
    },
  },
  watch: {
    // Reloading from a watcher rather than from the select's own handler
    // covers both ways these change: the user picking one, and the stored
    // settings arriving after this card has already drawn itself with the
    // defaults.
    filter() {
      this.loadData()
    },
    period() {
      this.loadData()
    },
  },
  // Not in data(): Vue 3 would wrap the Chart instance in a reactive proxy,
  // and Chart.js compares against the objects it registered itself, so an
  // update through the proxy silently repaints nothing. Plain instance
  // properties stay out of the reactivity system entirely.
  created() {
    this.jobchart = null;
  },
  mounted() {
    this.createChart();
  },
  beforeUnmount() {
    if (this.jobchart) {
      this.jobchart.destroy();
      this.jobchart = null;
    }
  },
  methods: {
    updateSettings() {
      // Persist only. The watcher above does the reload, so a change made
      // here and one arriving from the server take the same path.
      this.$store.commit("updateSettings")
    },
    markPlotted(labels) {
      // What is actually on the canvas, readable from the DOM. A canvas has
      // no inspectable content, so without this a chart that quietly failed
      // to repaint looks identical to one that did.
      if (this.$refs.chart) {
        this.$refs.chart.dataset.points = String((labels || []).length);
      }
    },
    chartParams() {
      let params = { params: { fun: this.filter, period: this.period } };
      if (this.minion) {
        params.params.id = this.minion;
      }
      return params;
    },
    loadData() {
      // The chart may not exist yet: its first fetch is still in flight when
      // stored settings land. Building it then is the same work.
      if (!this.jobchart) {
        return this.createChart();
      }
      this.$http.get("api/jobs/graph", this.chartParams()).then((response) => {
        this.jobchart.data.labels = response.data.labels;
        this.jobchart.data.datasets[0].data = response.data.series[0];
        this.jobchart.data.datasets[1].data = response.data.series[1];
        this.jobchart.update();
        this.markPlotted(response.data.labels);
      });
    },
    createChart() {
      if (this.jobchart != null) {
        this.jobchart.destroy();
        this.jobchart = null;
      }
      return this.$http.get("api/jobs/graph", this.chartParams()).then((response) => {
        let labels = response.data.labels;
        let series = response.data.series;
        this.$refs.chart.height = 60;
        this.jobchart = markRaw(new Chart(this.$refs.chart, {
          type: "line",
          data: {
            labels: labels,
            datasets: [
              {
                tension: 0.1,
                pointRadius: 1,
                data: series[0],
                fill: false,
                colorStart: "rgba(0, 173, 238, 1.0)",
                colorEnd: "rgba(231, 18, 143, 1.0)",
              },
              {
                tension: 0.1,
                pointRadius: 1,
                data: series[1],
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
        }));
        this.markPlotted(labels);
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
