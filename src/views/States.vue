<template>
  <v-container fluid>
    <v-row>
      <v-col sm="12">
        <StateDurationsTable></StateDurationsTable>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
  import StateDurationsTable from "../components/StateDurationsTable"

  export default {
    name: "States",
    components: { StateDurationsTable },
  }
</script>
