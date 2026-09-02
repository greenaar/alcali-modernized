<template>
  <v-card v-if="jobs.length || error" class="mb-4">
    <v-card-title class="d-flex align-center flex-wrap ga-3">
      {{ $t("components.ActiveJobsCard.Title") }}
      <v-chip v-if="jobs.length" color="warning">{{ jobs.length }}</v-chip>
      <v-spacer></v-spacer>
      <v-btn
        icon
        variant="text"
        size="small"
        :loading="loading"
        :title="$t('components.ActiveJobsCard.Refresh')"
        @click="load"
      >
        <v-icon>refresh</v-icon>
      </v-btn>
    </v-card-title>
    <v-card-text>
      <v-alert v-if="error" type="warning" class="mb-0">{{ error }}</v-alert>
      <v-table v-else density="compact">
        <thead>
          <tr>
            <th>{{ $t("components.ActiveJobsCard.Jid") }}</th>
            <th>{{ $t("components.ActiveJobsCard.Function") }}</th>
            <th>{{ $t("components.ActiveJobsCard.Target") }}</th>
            <th>{{ $t("components.ActiveJobsCard.User") }}</th>
            <th class="text-right">{{ $t("components.ActiveJobsCard.Minions") }}</th>
            <th class="text-right">{{ $t("components.ActiveJobsCard.Stop") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.jid">
            <td>
              <router-link :to="'/jobs/' + job.jid">{{ job.jid }}</router-link>
            </td>
            <td>{{ job.fun }}</td>
            <td>{{ job.target }}</td>
            <td>{{ job.user }}</td>
            <td class="text-right">{{ job.minions }}</td>
            <td class="text-right">
              <v-btn size="small" color="warning" variant="tonal"
                     @click="ask(job, 'term')">
                {{ $t("components.ActiveJobsCard.Stop") }}
              </v-btn>
              <v-btn size="small" color="error" variant="text" class="ml-2"
                     @click="ask(job, 'kill')">
                {{ $t("components.ActiveJobsCard.Force") }}
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card-text>

    <v-dialog v-model="confirm" width="560">
      <v-card v-if="pending">
        <v-card-title class="text-error">
          {{ $t("components.ActiveJobsCard.ConfirmTitle") }}
        </v-card-title>
        <v-card-text>
          <p>
            {{
              $t("components.ActiveJobsCard.ConfirmBody", [
                pending.job.fun,
                pending.job.minions,
                pending.job.target,
              ])
            }}
          </p>
          <p class="mb-0 text-medium-emphasis">
            {{
              pending.signal === "kill"
                ? $t("components.ActiveJobsCard.KillWarning")
                : $t("components.ActiveJobsCard.TermNote")
            }}
          </p>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="confirm = false">
            {{ $t("components.ActiveJobsCard.Cancel") }}
          </v-btn>
          <v-btn color="error" :loading="stopping" @click="stop">
            {{ $t("components.ActiveJobsCard.Confirm") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script>
export default {
  name: "ActiveJobsCard",
  data() {
    return {
      // A job reaches the returner only once it finishes, so the jobs table
      // cannot show what is in flight. This is the only view of that, and the
      // only place a run can be stopped.
      jobs: [],
      error: null,
      loading: false,
      stopping: false,
      confirm: false,
      pending: null,
    }
  },
  mounted() {
    this.load()
    // Short enough to be useful while watching a rollout, long enough not to
    // be a poll storm: every active job listing is a runner call on the master.
    this.timer = setInterval(this.load, 10000)
  },
  beforeUnmount() {
    clearInterval(this.timer)
  },
  methods: {
    load() {
      this.loading = true
      this.$http
        .get("api/jobs/active/")
        .then((response) => {
          this.jobs = response.data
          this.error = null
        })
        .catch((error) => {
          this.jobs = []
          this.error = this.errorText(error)
        })
        .then(() => {
          this.loading = false
        })
    },
    ask(job, signal) {
      this.pending = { job, signal }
      this.confirm = true
    },
    stop() {
      this.stopping = true
      this.$http
        .post("api/jobs/" + this.pending.job.jid + "/kill/", {
          signal: this.pending.signal,
        })
        .then((response) => {
          let stopped = response.data.stopped || []
          this.$toast(
            this.$i18n.t("components.ActiveJobsCard.Stopped", [stopped.length])
          )
          this.confirm = false
          this.load()
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
        .then(() => {
          this.stopping = false
        })
    },
    errorText(error) {
      let data = error.response && error.response.data
      return (data && (data.error || data.detail)) || String(error)
    },
  },
}
</script>
