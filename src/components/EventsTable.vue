<template>
  <v-container fluid>
    <v-card>
      <v-card-title>
        {{ $t("components.EventsTable.Events") }}
        <span v-if="total > events.length" class="text-caption text-medium-emphasis ml-3">
          {{ $t("components.EventsTable.ShowingLatest", [events.length, total]) }}
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
        v-model:sort-by="settings.EventsTable.table.sortBy"
        @update:sort-by="updateSettings"
        v-model:sort-desc="settings.EventsTable.table.sortDesc"
        @update:sort-desc="updateSettings"
        v-model:items-per-page="settings.EventsTable.table.itemsPerPage"
        @update:items-per-page="updateSettings"
        :headers="headers"
        :items="events"
        :search="search"
        item-value="id"
        class="elevation-1"
        show-expand
        :loading="loading"
      >
        <template v-slot:item.alter_time="{ item }">
          {{ new Date(item.alter_time).toLocaleString("en-GB") }}
        </template>
        <template v-slot:expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length">
              <pre>{{ JSON.stringify(safeParse(item.data), null, 2) }}</pre>
            </td>
          </tr>
        </template>
      </legacy-data-table>
    </v-card>
  </v-container>
</template>

<script>
import { mapState } from "vuex"

function parseEventData(json) {
  try {
    let parsed = JSON.parse(json);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (e) {
    return {};
  }
}

function addedData(data) {
  data.forEach((event) => {
    let parsed = parseEventData(event.data);
    for (let key in parsed) {
      if (key === "id") {
        event["minion_id"] = parsed[key];
      } else {
        event[key] = parsed[key];
      }
    }
    // salt/job/<jid>/new carries the arguments as `arg`, the return events as
    // `fun_args`; the table shows a single Arguments column for both.
    if (event.fun_args === undefined && parsed.arg !== undefined) {
      event.fun_args = parsed.arg;
    }
  });
  return data;
}

export default {
  name: "EventsTable",
  data() {
    return {
      search: "",
      headers: [
        { text: this.$i18n.t("components.EventsTable.Tag"), value: "tag" },
        { text: this.$i18n.t("components.EventsTable.Jid"), value: "jid" },
        {
          text: this.$i18n.t("components.EventsTable.Target"),
          value: "minion_id",
        },
        { text: this.$i18n.t("components.EventsTable.Function"), value: "fun" },
        {
          text: this.$i18n.t("components.EventsTable.Arguments"),
          value: "fun_args",
        },
        {
          text: this.$i18n.t("components.EventsTable.Date"),
          value: "alter_time",
        },
      ],
      events: [],
      total: 0,
      loading: true,
    };
  },
  mounted() {
    this.loadData();
  },
  methods: {
    updateSettings() {
      this.$store.commit("updateSettings")
    },
    loadData() {
      this.$http.get("api/events/", { params: { limit: 500 } }).then((response) => {
        this.events = addedData(response.data);
        // The endpoint returns a window on the newest rows; the header carries
        // how many there are in total so the count below is honest.
        this.total = Number(response.headers["x-total-count"]) || this.events.length;
        this.loading = false;
      });
    },
    safeParse(json) {
      return parseEventData(json);
    },
  },
  computed: {
    ...mapState({
      settings: state => state.settings,
    }),
  },
};
</script>

<style scoped>
</style>
