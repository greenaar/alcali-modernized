<template>
  <v-container fluid>
    <UserCard></UserCard>
    <AuditLogTable v-if="isStaff"></AuditLogTable>
  </v-container>
</template>

<script>
  import UserCard from "../components/UserCard"
  import AuditLogTable from "../components/AuditLogTable"

  export default {
    name: "Users",
    components: { UserCard, AuditLogTable },
    computed: {
      isStaff() {
        return this.$store.getters.isStaff
      },
    },
  }
</script>

<style scoped>

</style>