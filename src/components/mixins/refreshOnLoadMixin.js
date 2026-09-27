// Pages backed by Alcali's copy of master data (keys, grains, schedules,
// beacons) show whatever was last pulled. With `refresh_on_load` set, pull
// again as the page opens: the component's `refreshOnLoad()` runs once the
// stored settings are known, and should keep quiet unless something fails.
export default {
  mounted() {
    this.$store.dispatch("settingsReady").then(() => {
      if (this.$.isUnmounted) return
      if (this.$store.state.settings.UserSettings.refresh_on_load) {
        this.refreshOnLoad()
      }
    })
  },
}
