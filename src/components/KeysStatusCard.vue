<template>
  <v-container fluid>
    <v-card>
      <v-card-title>{{ $t('components.KeysStatusCard.keys') }}</v-card-title>
      <!-- A three column table could not fit "n / total" in a narrow card, so
           the counts were clipped off the right edge. -->
      <v-list density="compact" class="py-0 pb-2">
        <v-list-item
          v-for="(count, status) in keys_status"
          :key="status"
          :prepend-icon="statusIcon(status)"
        >
          <div class="d-flex align-center justify-space-between ga-2">
            <span>{{ $t(`components.KeysStatusCard.${status}`) }}</span>
            <span class="text-no-wrap font-weight-medium">
              {{ count }}<span class="text-medium-emphasis">&nbsp;/&nbsp;{{ keys_total }}</span>
            </span>
          </div>
        </v-list-item>
      </v-list>
    </v-card>
  </v-container>
</template>

<script>

  export default {
    name: "KeysStatusCard",
    data() {
      return {
        keys_status: {},
        keys_total: 0,
      }
    },
    mounted() {
      this.loadData()
    },
    methods: {
      loadData() {
        this.$http.get("api/keys/keys_status/").then(response => {
          this.keys_status = response.data
          this.keys_total = Object.values(response.data).reduce((acc, cur)=> acc + cur)
        })
      },
      statusIcon(status) {
        switch (status) {
          case "accepted":
            return "check"
          case "rejected":
            return "first_page"
          case "denied":
            return "close"
          case "unaccepted":
            return "refresh"
        }
      },
    },
  }
</script>

<style scoped>

</style>
