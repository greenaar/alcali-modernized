// Pages backed by Alcali's copy of master data (keys, grains, schedules,
// beacons) show whatever was last pulled. Where the user has refresh_on_load
// set for the page, pull again as it opens: the component names its entry in
// `refreshOnLoadPage` and its `refreshOnLoad()` runs once the stored settings
// are known, keeping quiet unless something fails.
export default {
  mounted() {
    this.$store.dispatch("settingsReady").then(() => {
      if (this.$.isUnmounted) return
      const pages = this.$store.state.settings.UserSettings.refresh_on_load
      if (pages[this.$options.refreshOnLoadPage]) {
        this.refreshOnLoad()
      }
    })
  },
}
