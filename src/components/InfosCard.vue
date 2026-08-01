<template>
  <v-container fluid>
    <v-card>
      <v-card-title>{{ minion.id }}</v-card-title>
      <v-tabs
          v-model="settings.MinionDetail.InfosCard.tab"
          @change="updateSettings"
      >
        <v-tabs-slider></v-tabs-slider>

        <v-tab value="common">
          {{ $t("components.InfosCard.Common") }}
        </v-tab>

        <v-tab value="salt">
          {{ $t("components.InfosCard.Salt") }}
        </v-tab>

        <v-tab value="hardware">
          {{ $t("components.InfosCard.Hardware") }}
        </v-tab>
      </v-tabs>
      <v-window v-model="settings.MinionDetail.InfosCard.tab">
        <v-window-item value="common">
          <v-table>
            <tbody>
              <tr v-for="item in common" :key="item.name">
                <td>{{ $t(item.name) }}</td>
                <td
                  v-if="item.grain === 'last_job' || (item.grain === 'last_highstate' && minion[item.grain] !== null)"
                  class="text-right"
                >
                  {{ new Date(minion[item.grain]).toLocaleString("en-GB") }}
                </td>
                <td v-else-if="item.grain === 'conformity'" class="text-right">
                  <v-chip :color="boolRepr(minion[item.grain])" dark>{{
                    minion[item.grain] == null ? "unknown" : minion[item.grain]
                  }}</v-chip>
                </td>
                <td v-else class="text-right">{{ minion[item.grain] }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>
        <v-window-item value="salt">
          <v-table>
            <tbody>
              <tr v-for="item in salt" :key="item.name">
                <td>{{ item.name }}</td>
                <td class="text-right">{{ minion[item.grain] }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>
        <v-window-item value="hardware">
          <v-table>
            <tbody>
              <tr v-for="item in hardware" :key="item.name">
                <td>{{ item.name }}</td>
                <td class="text-right">{{ minion[item.grain] }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>
      </v-window>
    </v-card>
  </v-container>
</template>

<script>
import { mapState } from "vuex"

export default {
  name: "InfosCard",
  data() {
    return {
      common: [
        { name: "F.Q.D.N", grain: "fqdn" },
        { name: "O.S", grain: "os" },
        { name: "O.S Version", grain: "oscodename" },
        { name: "Kernel", grain: "kernelrelease" },
        { name: "Last Job", grain: "last_job" },
        { name: "Last Highstate", grain: "last_highstate" },
        { name: "Highstate Conformity", grain: "conformity" },
      ],
      salt: [
        { name: "ID", grain: "id" },
        { name: "Master", grain: "master" },
        { name: "Salt Version", grain: "saltversion" },
        { name: "Salt Path", grain: "saltpath" },
        { name: "Python Version", grain: "pythonversion" },
      ],
      hardware: [
        { name: "C.P.U Model", grain: "cpu_model" },
        { name: "Number of C.P.U", grain: "num_cpus" },
        { name: "Total Memory", grain: "mem_total" },
        { name: "Total Swap", grain: "swap_total" },
        { name: "Virtual", grain: "virtual" },
      ],
    };
  },
  props: ["minion"],
  methods: {
    boolRepr(bool) {
      if (bool === "True") {
        return "green";
      } else if (bool === "False") {
        return "red";
      } else return "primary";
    },
    updateSettings() {
      this.$store.commit("updateSettings")
    },
  },
  computed: {
    ...mapState({
      settings: state => state.settings,
    }),
  },
};
</script>

<style scoped></style>
