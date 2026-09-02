<template>
  <v-container fluid>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-3">
        {{ $t("components.AuditLogTable.Title") }}
        <span class="text-caption text-medium-emphasis ml-3">
          {{ $t("components.AuditLogTable.Subtitle") }}
        </span>
        <v-spacer></v-spacer>
        <v-text-field
          class="search"
          v-model="search"
          append-icon="search"
          :label="$t('common.Search')"
          single-line
          hide-details
        ></v-text-field>
      </v-card-title>
      <legacy-data-table
        :headers="headers"
        :items="entries"
        :search="search"
        item-value="id"
        sort-by="created"
        sort-desc
        class="elevation-1"
        :loading="loading"
      >
        <template v-slot:item.created="{ item }">
          {{ new Date(item.created).toLocaleString("en-GB") }}
        </template>
        <template v-slot:item.action="{ item }">
          <v-chip size="small" label :color="actionColor(item.action)">
            {{ item.action }}
          </v-chip>
        </template>
      </legacy-data-table>
    </v-card>
  </v-container>
</template>

<script>
export default {
  name: "AuditLogTable",
  data() {
    return {
      search: "",
      entries: [],
      loading: true,
      headers: [
        { text: this.$t("components.AuditLogTable.When"), value: "created" },
        { text: this.$t("components.AuditLogTable.Who"), value: "username" },
        { text: this.$t("components.AuditLogTable.Action"), value: "action" },
        { text: this.$t("components.AuditLogTable.Target"), value: "target" },
      ],
    }
  },
  mounted() {
    this.loadData()
  },
  methods: {
    loadData() {
      this.$http
        .get("api/audit/")
        .then((response) => {
          this.entries = response.data
          this.loading = false
        })
        .catch(() => {
          this.loading = false
        })
    },
    actionColor(action) {
      if (action.endsWith(".delete") || action.startsWith("key.reject")) return "red"
      if (action.endsWith(".create") || action.startsWith("key.accept")) return "green"
      return "primary"
    },
  },
}
</script>
