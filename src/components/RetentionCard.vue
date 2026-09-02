<template>
  <v-container fluid>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-3">
        {{ $t("components.RetentionCard.Title") }}
        <span class="text-caption text-medium-emphasis">
          {{ $t("components.RetentionCard.Subtitle") }}
        </span>
      </v-card-title>
      <v-card-text>
        <v-row align="center">
          <v-col cols="12" sm="6" md="3">
            <v-text-field
              v-model.number="days"
              type="number"
              min="1"
              :label="$t('components.RetentionCard.KeepJobs')"
              :suffix="$t('components.RetentionCard.Days')"
              hide-details
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field
              v-model.number="eventsDays"
              type="number"
              min="1"
              :label="$t('components.RetentionCard.KeepEvents')"
              :suffix="$t('components.RetentionCard.Days')"
              hide-details
            ></v-text-field>
          </v-col>
          <v-col cols="12" md="6" class="d-flex ga-2">
            <v-btn
              variant="tonal"
              :loading="loading"
              :disabled="!validWindow"
              @click="preview"
            >
              {{ $t("components.RetentionCard.Preview") }}
            </v-btn>
            <v-btn
              color="error"
              :disabled="!matched || totalMatched === 0"
              @click="confirm = true"
            >
              {{ $t("components.RetentionCard.Delete") }}
            </v-btn>
          </v-col>
        </v-row>

        <v-table v-if="matched" density="compact" class="mt-4">
          <thead>
            <tr>
              <th>{{ $t("components.RetentionCard.Table") }}</th>
              <th class="text-right">{{ $t("components.RetentionCard.Matching") }}</th>
              <th class="text-right">{{ $t("components.RetentionCard.Total") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(count, table) in matched" :key="table">
              <td>{{ table }}</td>
              <td class="text-right">{{ count }}</td>
              <td class="text-right text-medium-emphasis">{{ totals[table] }}</td>
            </tr>
          </tbody>
        </v-table>
        <p v-if="matched && totalMatched === 0" class="text-medium-emphasis mt-3 mb-0">
          {{ $t("components.RetentionCard.NothingToRemove") }}
        </p>
      </v-card-text>
    </v-card>

    <v-dialog v-model="confirm" width="520">
      <v-card>
        <v-card-title class="text-error">
          {{ $t("components.RetentionCard.ConfirmTitle") }}
        </v-card-title>
        <v-card-text>
          {{ $t("components.RetentionCard.ConfirmBody", [totalMatched, days, eventsDays]) }}
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="confirm = false">
            {{ $t("components.RetentionCard.Cancel") }}
          </v-btn>
          <v-btn color="error" :loading="loading" @click="apply">
            {{ $t("components.RetentionCard.Delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
export default {
  name: "RetentionCard",
  data() {
    return {
      // Salt's mysql returner never removes anything, so these tables grow for
      // the life of the installation unless something prunes them.
      days: 90,
      eventsDays: 30,
      matched: null,
      totals: {},
      loading: false,
      confirm: false,
    }
  },
  computed: {
    validWindow() {
      return this.days >= 1 && this.eventsDays >= 1
    },
    totalMatched() {
      if (!this.matched) return 0
      return Object.values(this.matched).reduce((a, b) => a + b, 0)
    },
  },
  methods: {
    params() {
      return { days: this.days, events_days: this.eventsDays }
    },
    preview() {
      this.loading = true
      this.$http
        .get("api/prune/", { params: this.params() })
        .then((response) => {
          this.matched = response.data.matched
          this.totals = response.data.totals
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
        .then(() => {
          this.loading = false
        })
    },
    apply() {
      this.loading = true
      this.$http
        .post("api/prune/", this.params())
        .then((response) => {
          let removed = Object.values(response.data.deleted).reduce((a, b) => a + b, 0)
          this.$toast(this.$i18n.t("components.RetentionCard.Removed", [removed]))
          this.confirm = false
          this.preview()
        })
        .catch((error) => {
          this.confirm = false
          this.$toast.error(this.errorText(error))
        })
        .then(() => {
          this.loading = false
        })
    },
    errorText(error) {
      let data = error.response && error.response.data
      return (data && (data.error || data.detail)) || String(error)
    },
  },
}
</script>
