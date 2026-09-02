<template>
  <v-container fluid>
    <v-row>
      <v-col sm="12">
        <CommonSettings></CommonSettings>
      </v-col>
    </v-row>
    <v-row>
      <v-col sm="12">
        <UserSettings></UserSettings>
      </v-col>
    </v-row>
    <v-row v-if="isStaff">
      <v-col sm="12">
        <DiagnosticsCard></DiagnosticsCard>
      </v-col>
    </v-row>
    <v-row v-if="isStaff">
      <v-col sm="12">
        <RetentionCard></RetentionCard>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
  import CommonSettings from "../components/CommonSettings"
  import UserSettings from "../components/UserSettings"
  import RetentionCard from "../components/RetentionCard"
  import DiagnosticsCard from "../components/DiagnosticsCard"

  export default {
    name: "Settings",
    components: { UserSettings, CommonSettings, RetentionCard, DiagnosticsCard },
    computed: {
      isStaff() {
        return this.$store.getters.isStaff
      },
    },
  }
</script>

<style scoped>

</style>