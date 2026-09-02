<template>
  <v-container fluid>
    <v-card>
      <v-card-title>
        {{ $t("components.ConformityTable.Conformity") }}
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
        v-model:sort-by="settings.ConformityTable.table.sortBy"
        @update:sort-by="updateSettings"
        v-model:sort-desc="settings.ConformityTable.table.sortDesc"
        @update:sort-desc="updateSettings"
        v-model:items-per-page="settings.ConformityTable.table.itemsPerPage"
        @update:items-per-page="updateSettings"
        item-value="minion_id"
        :headers="headers"
        :items="conformity"
        :search="search"
        class="elevation-1"
        :loading="loading"
      >
        <template v-slot:item.minion_id="{ item }">
          <v-btn
            variant="text"
            size="small"
            class="text-none"
            :to="'/conformity/' + item.minion_id"
            >{{ item.minion_id }}</v-btn
          >
        </template>
        <template v-slot:item.last_highstate="{ item }">
          {{
            item.last_highstate === null
              ? ""
              : new Date(item.last_highstate).toLocaleString("en-GB")
          }}
        </template>
        <template v-slot:item.conformity="{ item }">
          <v-chip :color="boolRepr(item.conformity)"
            >{{ $t(`components.ConformityTable.${item.conformity}`) }}
          </v-chip>
        </template>
        <template v-slot:item.succeeded="{ item }">
          <v-chip
            class="ma-2"
            label
            outlined
            color="green"
            text-color="base"
            v-if="item.succeeded != null"
          >
            {{ item.succeeded }}
          </v-chip>
        </template>
        <template v-slot:item.unchanged="{ item }">
          <v-chip
            class="ma-2"
            label
            outlined
            color="orange"
            text-color="base"
            v-if="item.unchanged != null"
          >
            {{ item.unchanged }}
          </v-chip>
        </template>
        <template v-slot:item.failed="{ item }">
          <v-chip
            class="ma-2"
            label
            outlined
            color="red"
            text-color="base"
            v-if="item.failed != null"
          >
            {{ item.failed }}
          </v-chip>
        </template>
        <template v-slot:item.action="{ item }">
          <div class="d-flex flex-nowrap justify-end ga-1">
            <v-btn variant="tonal"
              size="small"
             
              color="blue"
             
             
              :to="'/conformity/' + item.minion_id"
            >
              {{ $t("components.ConformityTable.detail") }}
            </v-btn>
            <v-btn variant="tonal"
              size="small"
             
              color="orange"
             
             
              :to="'/run?tgt=' + item.minion_id + '&fun=state.apply'"
            >
              {{ $t("components.ConformityTable.highstate") }}
            </v-btn>
          </div>
        </template>
      </legacy-data-table>
    </v-card>
  </v-container>
</template>

<script>
import { mapState } from "vuex"

export default {
  name: "ConformityTable",
  data() {
    return {
      search: "",
      headers: [],
      conformity: [],
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
      this.$http.get("api/conformity/render/").then((response) => {
        this.headers = response.data.name.map((dataItem) => {
          return {
            ...dataItem,
            text: dataItem.text,
          };
        });
        this.headers.push({
          text: this.$i18n.t("components.ConformityTable.Actions"),
          value: "action",
          sortable: false,
        });
        this.conformity = response.data.data;
        this.loading = false;
      });
    },
    boolRepr(bool) {
      if (bool === "True") {
        return "green";
      } else if (bool === "False") {
        return "red";
      } else return "primary";
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
