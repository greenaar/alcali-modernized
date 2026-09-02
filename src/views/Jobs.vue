<template>
  <v-container fluid>
    <v-row>
      <v-col sm="12" cols="12">
        <ActiveJobsCard></ActiveJobsCard>
        <JobsTable :jid="jid"></JobsTable>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
  import ActiveJobsCard from "../components/ActiveJobsCard"
  import JobsTable from "../components/JobsTable"

  export default {
    name: "Jobs",
    props: ["jid"],
    components: {
      ActiveJobsCard,
      JobsTable,
    },
  }

</script>

<style scoped>

</style>