<template>
  <v-container fluid>
    <v-card>
      <v-tabs
          v-model="settings.MinionDetail.MinionDetailCard.tab"
          @change="updateSettings"
      >
      <v-tabs-slider></v-tabs-slider>

        <v-tab value="grain">
          {{ $t("components.MinionDetailCard.Grains") }}
        </v-tab>

        <v-tab value="pillar">
          {{ $t("components.MinionDetailCard.Pillar") }}
        </v-tab>
        <v-tab value="history">
          {{ $t("components.MinionDetailCard.History") }}
        </v-tab>
        <v-tab value="graph">
          {{ $t("components.MinionDetailCard.Graph") }}
        </v-tab>
        <v-tab v-for="field in minion.custom_fields" :key="field.name" :value="field.name">
          {{ field.name }}
        </v-tab>
      </v-tabs>
      <v-window v-model="settings.MinionDetail.MinionDetailCard.tab">
        <v-window-item value="grain">
          <div class="text-right">
            <v-btn @click="fold('grainCm')" class="overlayedBtn">{{
              grainCmFolded ? $t("components.MinionDetailCard.Unfold") : $t("components.MinionDetailCard.Fold")
            }}</v-btn>
          </div>
          <yaml-editor v-model="code" :read-only="true" :collapsed="grainCmFolded"></yaml-editor>
        </v-window-item>
        <v-window-item value="pillar">
          <div class="text-right">
            <v-btn @click="fold('pillarCm')" class="overlayedBtn">{{
              pillarCmFolded ? $t("components.MinionDetailCard.Unfold") : $t("components.MinionDetailCard.Fold")
            }}</v-btn>
          </div>
          <yaml-editor v-model="codepillar" :read-only="true" :collapsed="pillarCmFolded"></yaml-editor>
        </v-window-item>
        <v-window-item value="history">
          <JobsTable :filter="{ 'target[]': minion.minion_id }"></JobsTable>
        </v-window-item>
        <v-window-item value="graph" eager>
          <JobsChartCard v-if="minion" :minion="minion.minion_id"></JobsChartCard>
        </v-window-item>
        <v-window-item v-for="field in minion.custom_fields" :key="field.name" :value="field.name">
          <yaml-editor :read-only="true" :model-value="yamlRepr(field.value)"></yaml-editor>
        </v-window-item>
      </v-window>
    </v-card>
  </v-container>
</template>

<script>
import { mapState } from "vuex"

import yaml from "js-yaml";
import JobsChartCard from "./JobsChartCard";
import JobsTable from "./JobsTable";
import YamlEditor from "./YamlEditor";

export default {
  name: "MinionDetailCard",
  components: {
    JobsTable,
    JobsChartCard,
    YamlEditor,
  },
  data() {
    return {
      code: yaml.dump(JSON.parse(this.minion.grain)),
      codepillar: yaml.dump(JSON.parse(this.minion.pillar)),
      grainCmFolded: false,
      pillarCmFolded: false,
    };
  },
  methods: {
    updateSettings() {
      this.$store.commit("updateSettings")
    },
    yamlRepr(data) {
      return yaml.dump(JSON.parse(data));
    },
    fold(ref) {
      this[ref + "Folded"] = !this[ref + "Folded"];
    },
  },
  computed: {
    ...mapState({
      settings: state => state.settings,
    }),
  },
  props: ["minion"],
};
</script>

<style scoped>
.overlayedBtn {
  position: absolute;
  right: 0;
  z-index: 1;
}
</style>
