<template>
  <v-container fluid>
    <v-card>
      <v-card-title>{{ $t("components.NetworkCard.Network") }}</v-card-title>
      <v-tabs
          v-model="settings.MinionDetail.NetworkCard.tab"
          @change="updateSettings"
      >
      <v-tabs-slider></v-tabs-slider>

        <v-tab value="interface">
          {{ $t("components.NetworkCard.Interface") }}
        </v-tab>

        <v-tab value="mac">
          {{ $t("components.NetworkCard.MAC") }}
        </v-tab>

        <v-tab value="dns">
          {{ $t("components.NetworkCard.DNS") }}
        </v-tab>
      </v-tabs>
      <v-window v-model="settings.MinionDetail.NetworkCard.tab">
        <v-window-item value="interface">
          <v-table>
            <tbody>
              <tr v-for="(val, key) in minion.ip_interfaces" :key="key">
                <td>{{ key }}</td>
                <td class="text-right" v-for="(iface, k) in val" :key="k">{{ iface }}</td>
              </tr>
              <tr>
                <td>{{ $t("components.NetworkCard.IPV4Gateway") }}</td>
                <td class="text-right">{{ minion.ip4_gw }}</td>
              </tr>
              <tr>
                <td>{{ $t("components.NetworkCard.IPV6Gateway") }}</td>
                <td class="text-right">{{ minion.ip6_gw }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>
        <v-window-item value="mac">
          <v-table>
            <tbody>
              <tr v-for="(val, key) in minion.hwaddr_interfaces" :key="key">
                <td>{{ key }}</td>
                <td class="text-right">{{ val }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-window-item>
        <v-window-item value="dns">
          <v-table>
            <tbody>
              <tr v-for="(val, key) in minion.dns" :key="key">
                <td>{{ key }}</td>
                <td class="text-right">{{ val.length >= 1 ? val : "" }}</td>
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
  name: "NetworkCard",
  data() {
    return {
      tab: null,
      tabs: 3,
    };
  },
  props: ["minion"],
  methods: {
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
