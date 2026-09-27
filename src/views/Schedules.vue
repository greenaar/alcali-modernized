<template>
  <v-container fluid>
    <v-row>
      <v-col sm="12">
        <ScheduleTable :key="refreshKey"></ScheduleTable>
        <Fab v-if="fabs" :fabs="fabs" v-on:fab_action="fabAction"></Fab>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
  import ScheduleTable from "../components/ScheduleTable"
  import Fab from "../components/core/Fab"
  import refreshOnLoadMixin from "../components/mixins/refreshOnLoadMixin"

  export default {
    name: "Schedules",
    components: { Fab, ScheduleTable },
    mixins: [refreshOnLoadMixin],
    data() {
      return {
        fabs: [
          {
            color: "pink",
            action: "refreshSchedules",
            icon: "refresh",
            tooltip: this.$i18n.t("components.Schedules.Refresh"),
          },
        ],
        refreshKey: 0,
      }
    },
    methods: {
      fabAction(action) {
        this[action]()
      },
      refreshOnLoad() {
        this.refreshSchedules(true)
      },
      refreshSchedules(quiet = false) {
        if (!quiet) this.$toast(this.$i18n.t("components.Schedules.Refreshing"))
        this.$http.post("/api/schedules/refresh/").then((response) => {
          this.refreshKey += 1
          if (response.data.no_minions_replied) {
            this.$toast.error(this.$i18n.t("components.Minions.NoMinionsReplied"))
          } else if (!quiet) {
            this.$toast(this.$i18n.t("components.Schedules.Refreshed"))
          }
        }).catch((error) => {
          this.$toast.error(error.response.data)
        })

      },
    },
  }
</script>

<style scoped>

</style>