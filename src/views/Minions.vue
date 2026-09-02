<template>
  <v-container fluid>
    <v-row>
      <v-col sm="12" cols="12">
        <MinionsTable :key="refreshKey"></MinionsTable>
        <Fab v-if="fabs" :fabs="fabs" v-on:fab_action="fabAction"></Fab>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
  import MinionsTable from "../components/MinionsTable"
  import Fab from "../components/core/Fab"

  export default {
    name: "Minions",
    components: { Fab, MinionsTable },
    data() {
      return {
        refreshKey: 0,
        fabs: [
          {
            color: "pink",
            action: "refreshMinions",
            icon: "refresh",
            tooltip: this.$i18n.t("components.Minions.RefreshAll")
          },
          {
            color: "orange",
            action: "runAll",
            icon: "playlist_play",
            tooltip: this.$i18n.t("components.Minions.JobAll"),
          },
        ],
      }
    }  ,
    methods: {
      fabAction(action) {
        this[action]()
      },
      refreshMinions() {
        this.$toast(this.$i18n.t("components.Minions.Refreshing"))
        this.$http.post("/api/minions/refresh_minions/").then((response) => {
          // "0 minions refreshed" reads like success. A master that answers
          // with nobody almost always means it could not read the job back.
          if (response.data.source === "master cache") {
            // The fallback populated the table. Reporting that as a failure,
            // which it did, is worse than saying nothing: the page fills in
            // while the toast says nothing replied.
            this.$toast(
              this.$i18n.t("components.Minions.RefreshedFromCache", [
                response.data.refreshed.length,
              ])
            )
          } else if (response.data.no_minions_replied) {
            let detail = response.data.cache_error
            this.$toast.error(
              this.$i18n.t("components.Minions.NoMinionsReplied") +
                (detail ? " " + detail : "")
            )
          } else {
            this.$toast(this.$i18n.t("components.Minions.NbMinionsRefreshed", [response.data.refreshed.length]))
          }
        }).then(() => {
          this.refreshKey += 1
        }).catch((error) => {
          this.$toast.error(error.response.data)
        })
      },
      runAll() {
        this.$router.push("/run?tgt=*")
      },
    },
  }
</script>

<style scoped>

</style>