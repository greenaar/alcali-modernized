<template>
  <v-container fluid>
    <v-card>
      <v-card-title>{{ $t('components.ConformityChart.conformity') }}</v-card-title>
      <v-card-text>
        <v-container fluid>
          <template v-for="name in conformitynames" :key="name">
            <v-row no-gutters align="center" justify="center">
              <v-col sm="2">{{name}}</v-col>
              <v-col sm="10">
                <v-menu open-on-hover max-width="250px">
                  <template v-slot:activator="{ props }">
                    <canvas :ref="name" height="15" v-bind="props"></canvas>
                  </template>
                  <v-table density="compact">
                    <thead>
                    <tr>
                      <th>{{name}}</th>
                    </tr>
                    </thead>
                    <tbody v-html="$sanitize(customTool)">
                    </tbody>
                  </v-table>
                </v-menu>
              </v-col>
            </v-row>
          </template>
        </v-container>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script>
  import { Chart, registerables } from "chart.js"
  import ChartjsPluginStacked100 from "chartjs-plugin-stacked100"

  import colors from "vuetify/util/colors"

  Chart.register(...registerables, ChartjsPluginStacked100)

  export default {
    name: "ConformityChart",
    data() {
      return {
        conformitynames: null,
        confchart: null,
        conformity: null,
        customTool: "",
      }
    },
    created() {

    },
    mounted() {
      this.loadConformity()
    },
    methods: {
      loadConformity() {
        this.$http.get("api/minions/conformity/").then(response => {
          this.conformity = response.data.data
          this.conformitynames = response.data.name
        }).then(() => {
          this.conformity.forEach((conformity, idx) => {
            let chart_data = {
              labels: [this.conformitynames[idx]],
              datasets: [],
            }
            Object.keys(conformity).forEach((value) => {
              let color = ""
              if (["conflict", "false"].indexOf(value) >= 0) {
                color = "#F44336"
              } else if (["conform", "true"].indexOf(value) >= 0) {
                color = "#41f40e"
              } else if (["None", "unknown", "null"].indexOf(value) >= 0) {
                color = this.$vuetify.theme.current.colors.primary
              } else {
                let keys = Object.keys(colors)
                color = colors[keys[keys.length * Math.random() << 0]].darken2
              }
              chart_data.datasets.push({
                label: value,
                data: [conformity[value]],
                backgroundColor: color,
              })
            })
            new Chart(this.$refs[this.conformitynames[idx]], {
              type: "bar",
              data: chart_data,
              options: {
                animation: false,
                indexAxis: "y",
                plugins: {
                  stacked100: { enable: true },
                  legend: { display: false },
                  tooltip: {
                    enabled: false,
                    mode: "index",
                    intersect: false,
                    external: ({ tooltip }) => {
                    if (!tooltip) {
                      return
                    }
                    if (tooltip.body) {
                      let bodyLines = tooltip.body.map(lines => lines.lines)

                      let innerHtml = ""

                      bodyLines.forEach(function(body, i) {
                        let colors = tooltip.labelColors[i]
                        let style = "background:" + colors.backgroundColor
                        style += "; border-color:" + colors.borderColor
                        style += "; border-width: 2px"
                        let span = `<span class="chartjs-tooltip-key" style="${style}">__</span>`
                        innerHtml += "<tr><td>" + span + "  " + body + "</td></tr>"
                      })
                      this.customTool = innerHtml
                    }
                  },
                },
                },
                scales: {
                  x: {
                    stacked: true,
                    display: false,
                    grid: {
                      display: false,
                      drawTicks: false,
                      drawBorder: false,
                    },
                    ticks: {
                      display: false,
                      padding: -20,
                    },
                  },
                  y: {
                    stacked: true,
                    display: false,
                    ticks: {
                      display: false,
                      padding: -20,
                    },
                    grid: {
                      drawTicks: false,
                      display: false,
                      drawBorder: false,
                    },
                  },
                },
              },
            })
          })
        })
      },
    },
  }
</script>

<style scoped>
  .v-menu--inline {
    display: block;
  }

  .chartjs-tooltip-key {
    display: inline-block;
    width: 10px;
    height: 10px;
    margin-right: 10px;
  }

</style>
