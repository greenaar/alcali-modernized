<template>
  <v-container fluid>
    <v-row>
      <v-col cols="12" lg="6">
        <ConformityChart></ConformityChart>
      </v-col>
      <!-- The key card was a twelfth wide, which left no room for the status
           labels next to their counts. -->
      <v-col cols="12" sm="6" lg="3">
        <KeysStatusCard></KeysStatusCard>
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <AlcaliStatusCard></AlcaliStatusCard>
      </v-col>
    </v-row>
    <v-row>
      <v-col cols="12" lg="4">
        <SilentMinionsCard></SilentMinionsCard>
      </v-col>
      <v-col cols="12" lg="8">
        <JobsChartCard></JobsChartCard>
      </v-col>
    </v-row>
    <v-row>
      <v-col lg="12">
        <JobsTable :filter="{limit: 10}"></JobsTable>
      </v-col>
    </v-row>

  </v-container>
</template>

<script>
  // @ is an alias to /src

  import KeysStatusCard from "../components/KeysStatusCard"
  import JobsChartCard from "../components/JobsChartCard"
  import AlcaliStatusCard from "../components/AlcaliStatusCard"
  import ConformityChart from "../components/ConformityChart"
  import JobsTable from "../components/JobsTable"
  import SilentMinionsCard from "../components/SilentMinionsCard"

  export default {
    name: "home",
    components: {
      JobsTable,
      SilentMinionsCard,
      ConformityChart,
      AlcaliStatusCard,
      KeysStatusCard,
      JobsChartCard,
    },
  }
</script>
