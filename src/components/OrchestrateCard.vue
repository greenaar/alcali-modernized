<template>
  <v-container fluid>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-3">
        {{ $t("components.OrchestrateCard.Title") }}
        <span class="text-caption text-medium-emphasis">
          {{ $t("components.OrchestrateCard.Subtitle") }}
        </span>
      </v-card-title>
      <v-card-text>
        <v-row dense align="center">
          <v-col cols="12" md="5">
            <!-- Free text as well as a list: the file server's view is a
                 convenience, not a restriction. -->
            <v-combobox
              v-model="sls"
              :items="states"
              :loading="loadingStates"
              :label="$t('components.OrchestrateCard.Sls')"
              :hint="slsHint"
              persistent-hint
              hide-no-data
            ></v-combobox>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field
              v-model="saltenv"
              :label="$t('components.OrchestrateCard.Saltenv')"
              @change="loadStates"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="4" class="d-flex align-center ga-2">
            <v-switch
              v-model="test"
              color="primary"
              hide-details
              :label="$t('components.OrchestrateCard.Test')"
            ></v-switch>
          </v-col>
        </v-row>
        <v-row dense>
          <v-col cols="12">
            <v-text-field
              v-model="pillar"
              :label="$t('components.OrchestrateCard.Pillar')"
              :placeholder="pillarPlaceholder"
              persistent-placeholder
            ></v-text-field>
          </v-col>
        </v-row>
        <v-row dense align="center">
          <v-col cols="12" class="d-flex align-center ga-3 flex-wrap">
            <v-btn
              :color="test ? 'primary' : 'error'"
              :disabled="!sls"
              :loading="running"
              @click="test ? run() : (confirm = true)"
            >
              {{
                test
                  ? $t("components.OrchestrateCard.DryRun")
                  : $t("components.OrchestrateCard.Apply")
              }}
            </v-btn>
            <code class="text-caption text-medium-emphasis">{{ command }}</code>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card v-if="results" class="mt-4">
      <v-card-title class="d-flex align-center">
        {{ $t("components.OrchestrateCard.Output") }}
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="results = ''">
          {{ $t("components.OrchestrateCard.Clear") }}
        </v-btn>
      </v-card-title>
      <v-card-text v-html="$sanitize(results)" class="ansiStyle"></v-card-text>
    </v-card>

    <v-dialog v-model="confirm" width="560">
      <v-card>
        <v-card-title class="text-error">
          {{ $t("components.OrchestrateCard.ConfirmTitle") }}
        </v-card-title>
        <v-card-text>
          {{ $t("components.OrchestrateCard.ConfirmBody", [sls]) }}
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="confirm = false">
            {{ $t("components.OrchestrateCard.Cancel") }}
          </v-btn>
          <v-btn variant="tonal" @click="confirm = false; test = true; run()">
            {{ $t("components.OrchestrateCard.RunDryInstead") }}
          </v-btn>
          <v-btn color="error" :loading="running" @click="confirm = false; run()">
            {{ $t("components.OrchestrateCard.Apply") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
export default {
  name: "OrchestrateCard",
  data() {
    return {
      sls: "",
      saltenv: "base",
      // Defaults to a dry run. An orchestration drives a whole fleet from one
      // command, so the safe reading of an accidental click is "show me".
      test: true,
      pillar: "",
      // In data rather than inline: the quoting an example needs does not
      // survive being written into a template attribute.
      pillarPlaceholder: '{"version": "1.2.3"}',
      states: [],
      statesUnavailable: false,
      loadingStates: false,
      running: false,
      confirm: false,
      results: "",
    }
  },
  computed: {
    command() {
      let name = this.sls
      if (name && Object.prototype.hasOwnProperty.call(name, "title")) {
        name = name.title
      }
      let parts = ["salt --client=runner state.orchestrate", name || "<sls>"]
      if (this.saltenv && this.saltenv !== "base") {
        parts.push("saltenv=" + this.saltenv)
      }
      if (this.test) parts.push("test=True")
      if (this.pillar) parts.push("pillar='" + this.pillar + "'")
      return parts.join(" ")
    },
    slsHint() {
      if (this.statesUnavailable) {
        return this.$t("components.OrchestrateCard.StatesUnavailable")
      }
      if (!this.states.length) return ""
      return this.$t("components.OrchestrateCard.StatesAvailable", [
        this.states.length,
      ])
    },
  },
  mounted() {
    this.loadStates()
  },
  methods: {
    loadStates() {
      this.loadingStates = true
      this.$http
        .get("api/states/available/", { params: { saltenv: this.saltenv } })
        .then((response) => {
          this.states = response.data.states || []
          this.statesUnavailable = !!response.data.unavailable
        })
        .catch(() => {
          this.states = []
          this.statesUnavailable = true
        })
        .then(() => {
          this.loadingStates = false
        })
    },
    run() {
      // Goes through the same endpoint as the Run page, so the output
      // rendering, the audit trail and the job record are all identical.
      let formData = new FormData()
      formData.set("raw", true)
      formData.set("command", this.command)
      this.running = true
      this.$http
        .post("api/run/", formData)
        .then((response) => {
          this.results = response.data + this.results
        })
        .catch((error) => {
          let data = error.response && error.response.data
          this.$toast.error((data && (data.error || data)) || String(error))
        })
        .then(() => {
          this.running = false
        })
    },
  },
}
</script>

<style scoped>
.ansiStyle {
  font-family: monospace;
  white-space: pre-wrap;
  overflow-x: auto;
}
</style>
