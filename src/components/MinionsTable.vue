<template>
  <v-container fluid>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-3">
        {{ $t("components.MinionsTable.Minion") }}
        <v-spacer></v-spacer>
        <v-menu v-model="menu" :close-on-content-click="false" offset-y offset-x left>
          <template v-slot:activator="{ props }">
            <v-btn color="primary" variant="tonal" v-bind="props">
              {{ $t("components.MinionsTable.Column") }}
            </v-btn>
          </template>

          <v-card flat max-width="700">
            <v-card-text>
              <v-container fluid>
                <v-row no-gutters>
                  <template v-for="(item, index) in available_headers" :key="index">
                    <v-col cols="4">
                      <v-checkbox :label="item" :value="item" v-model="settings.MinionsTable.table.columns"
                                  @update:model-value="updateSettings" hide-details></v-checkbox>
                    </v-col>
                  </template>
                </v-row>
              </v-container>
            </v-card-text>
          </v-card>
        </v-menu>
        <v-text-field
          v-model="search"
          append-icon="search"
          :label="$t('common.Search')"
          single-line
          hide-details
          class="search"
        ></v-text-field>
      </v-card-title>
      <legacy-data-table
        v-model:sort-by="settings.MinionsTable.table.sortBy"
        @update:sort-by="updateSettings"
        :headers="customHeaders"
        v-model:sort-desc="settings.MinionsTable.table.sortDesc"
        @update:sort-desc="updateSettings"
        :items="minions"
        v-model:items-per-page="settings.MinionsTable.table.itemsPerPage"
        @update:items-per-page="updateSettings"
        :search="search"
        class="elevation-1"
        :loading="loading"
        loading-text="Loading... Please wait"
      >
        <template v-slot:item.minion_id="{ item }">
          <v-btn variant="text" size="small" class="text-none" :to="'/minions/' + item.minion_id">{{ item.minion_id }}</v-btn>
        </template>
        <template v-slot:item.conformity="{ item }">
          <v-chip :color="boolRepr(item.conformity)" :to="'/conformity/'+item.minion_id">{{ $t(`components.ConformityTable.${item.conformity}`) }}
          </v-chip>
        </template>
        <template v-slot:item.last_job="{ item }">
          {{ item.last_job === null ? "" : new Date(item.last_job).toLocaleString("en-GB") }}
        </template>
        <template v-slot:item.last_highstate="{ item }">
          {{ item.last_highstate === null ? "" : new Date(item.last_highstate).toLocaleString("en-GB") }}
        </template>
        <template v-slot:item.action="{ item }">
          <!-- Four labelled buttons could not fit the actions column beside
               eight data columns, so they wrapped one per line and made every
               row four rows tall. -->
          <div class="d-flex flex-nowrap justify-end ga-1">
            <v-tooltip
              v-for="action in rowActions(item)"
              :key="action.key"
              :text="action.label"
              location="top"
            >
              <template v-slot:activator="{ props }">
                <v-btn
                  v-bind="props"
                  :icon="action.icon"
                  :color="action.color"
                  :to="action.to"
                  variant="text"
                  size="small"
                  density="comfortable"
                  @click="action.run && action.run()"
                ></v-btn>
              </template>
            </v-tooltip>
          </div>
        </template>
      </legacy-data-table>
    </v-card>
    <div class="d-flex flex-nowrap justify-end ga-1">
      <v-dialog v-model="dialog" width="500">
        <v-card>
          <v-card-title class="headline red" primary-title>
            {{ $t("components.MinionsTable.Delete") }} {{ target }} ?
          </v-card-title>

          <v-card-text>
            <br />
            {{ $t("components.MinionsTable.Msg1") }}{{ target }}{{ $t("components.MinionsTable.Msg2") }}
          </v-card-text>

          <v-divider></v-divider>

          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn color="primary" variant="text" @click="dialog = false">
              {{ $t("components.MinionsTable.Close") }}
            </v-btn>
            <v-btn color="red" variant="text" @click="deleteMinion(target)">
              {{ $t("components.MinionsTable.Delete") }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>
  </v-container>
</template>

<script>
import { mapState } from "vuex"

export default {
  name: "MinionsTable",
  data() {
    return {
      search: "",
      dialog: false,
      default_headers: [
        "minion_id",
        "conformity",
        "fqdn",
        "os",
        "oscodename",
        "kernelrelease",
        "last_job",
        "last_highstate",
      ],
      unwanted_headers: ["pillar", "grain", "id"],
      available_headers: [],
      minions: [],
      menu: false,
      target: null,
      loading: true,
    };
  },
  computed: {
    customHeaders() {
      let custom = [];
      this.settings.MinionsTable.table.columns.forEach((header) => {
        let titled = header
          .split("_")
          .map((title) => title.replace(/^\w/, (c) => c.toUpperCase()))
          .join(" ");
        custom.push({ text: titled, value: header });
      });
      // Wide enough for the four icon buttons; without it the last one is
      // clipped out of the column entirely.
      custom.push({
        text: this.$t("components.MinionsTable.Actions"),
        value: "action",
        sortable: false,
        width: 170,
        align: "end",
      });
      return custom;
    },
    ...mapState({
      settings: state => state.settings
    })
  },
  mounted() {
    this.loadData();
  },
  methods: {
    rowActions(item) {
      return [
        {
          key: "refresh",
          icon: "refresh",
          color: "primary",
          label: this.$t("components.MinionsTable.Refresh"),
          run: () => this.refreshMinion(item.minion_id),
        },
        {
          key: "detail",
          icon: "info",
          color: "",
          label: this.$t("components.MinionsTable.Detail"),
          to: "/minions/" + item.minion_id,
        },
        {
          key: "run",
          icon: "play_arrow",
          color: "",
          label: this.$t("components.MinionsTable.Run"),
          to: "/run?tgt=" + item.minion_id,
        },
        {
          key: "delete",
          icon: "delete",
          color: "error",
          label: this.$t("components.MinionsTable.Delete"),
          run: () => this.showDialog(item.minion_id),
        },
      ]
    },
    updateSettings() {
      this.$store.commit('updateSettings')
    },
    loadData() {
      this.$http.get("api/minions/").then((response) => {
        // A minion whose grains failed to serialise must not take the whole
        // table down with it.
        function addedGrains(data) {
          data.forEach((min) => {
            let grain;
            try {
              grain = JSON.parse(min.grain);
            } catch (e) {
              return;
            }
            if (!grain || typeof grain !== "object") {
              return;
            }
            for (let key in grain) {
              min[key] = grain[key];
            }
          });
          return data;
        }

        this.minions = addedGrains(response.data);
        this.loading = false;
        // Compute available headers
        this.available_headers = this.available_headers.concat(this.default_headers);
        if (this.minions.length > 0) {
          Object.keys(this.minions[0]).forEach((key) => {
            if (
              typeof this.minions[0][key] === "string" &&
              !this.default_headers.includes(key) &&
              !this.unwanted_headers.includes(key) &&
              !key.startsWith("lsb")
            ) {
              this.available_headers.push(key);
            }
          });
        }
      });
    },
    boolRepr(bool) {
      if (bool === "True") {
        return "green";
      } else if (bool === "False") {
        return "red";
      } else return "primary";
    },
    refreshMinion(minion_id) {
      this.$toast(this.$i18n.t("components.MinionsTable.Refreshing") + minion_id);
      let formData = new FormData();
      formData.set("minion_id", minion_id);
      this.$http
        .post("/api/minions/refresh_minions/", formData)
        .then((response) => {
          this.$toast(response.data.result);
        })
        .catch((error) => {
          this.$toast.error(error.response.data);
        });
    },
    deleteMinion(minion_id) {
      this.dialog = false;
      this.$http
        .delete(`/api/minions/${minion_id}/`)
        .then(() => {
          this.minions.splice(this.minions.indexOf(minion_id), 1);
          this.$toast(minion_id + this.$i18n.t("components.MinionsTable.Deleted"));
        })
        .catch((error) => {
          this.$toast.error(error.response.data);
        });
    },
    showDialog(minion_id) {
      this.target = minion_id;
      this.dialog = true;
    },
  },
};
</script>


<style scoped></style>
