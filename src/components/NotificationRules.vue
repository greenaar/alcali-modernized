<template>
  <v-container fluid>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-3">
        {{ $t("components.NotificationRules.Title") }}
        <span class="text-caption text-medium-emphasis">
          {{ $t("components.NotificationRules.Subtitle") }}
        </span>
        <v-spacer></v-spacer>
        <v-btn variant="text" :loading="previewing" @click="preview">
          {{ $t("components.NotificationRules.Preview") }}
        </v-btn>
        <v-btn color="primary" @click="open()">
          {{ $t("components.NotificationRules.Add") }}
        </v-btn>
      </v-card-title>
      <v-card-text>
        <v-alert v-if="previewEvents" type="info" class="mb-4" closable
                 @click:close="previewEvents = null">
          <div v-if="!previewEvents.length">
            {{ $t("components.NotificationRules.PreviewNothing") }}
          </div>
          <div v-else>
            <p class="mb-1">
              {{ $t("components.NotificationRules.PreviewSome", [previewEvents.length]) }}
            </p>
            <ul class="ml-4">
              <li v-for="event in previewEvents" :key="event.rule + event.minion">
                {{ event.minion }} - {{ event.reason }} ({{ event.rule }})
              </li>
            </ul>
          </div>
        </v-alert>

        <v-table density="compact">
          <thead>
            <tr>
              <th>{{ $t("components.NotificationRules.Name") }}</th>
              <th>{{ $t("components.NotificationRules.When") }}</th>
              <th>{{ $t("components.NotificationRules.Where") }}</th>
              <th class="text-right">{{ $t("components.NotificationRules.Actions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in rules" :key="rule.id">
              <td>
                {{ rule.name }}
                <v-chip v-if="!rule.enabled" size="x-small" class="ml-2">
                  {{ $t("components.NotificationRules.Disabled") }}
                </v-chip>
              </td>
              <td>{{ describe(rule) }}</td>
              <td class="text-caption">{{ channels(rule) }}</td>
              <td class="text-right">
                <div class="d-flex flex-nowrap justify-end ga-1">
                  <v-btn size="small" variant="text" :loading="testing === rule.id"
                         @click="sendTest(rule)">
                    {{ $t("components.NotificationRules.Test") }}
                  </v-btn>
                  <v-btn size="small" variant="tonal" @click="open(rule)">
                    {{ $t("components.NotificationRules.Edit") }}
                  </v-btn>
                  <v-btn size="small" variant="text" color="error"
                         @click="remove(rule)">
                    {{ $t("components.NotificationRules.Delete") }}
                  </v-btn>
                </div>
              </td>
            </tr>
          </tbody>
        </v-table>
        <p v-if="!rules.length" class="text-medium-emphasis mt-3 mb-0">
          {{ $t("components.NotificationRules.Empty") }}
        </p>
        <p class="text-caption text-medium-emphasis mt-4 mb-0">
          {{ $t("components.NotificationRules.Cron") }}
          <code>python manage.py alcali_notify</code>
        </p>
      </v-card-text>
    </v-card>

    <v-dialog v-model="dialog" width="640">
      <v-card>
        <v-card-title>
          {{
            draft.id
              ? $t("components.NotificationRules.EditTitle")
              : $t("components.NotificationRules.AddTitle")
          }}
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="draft.name"
            :label="$t('components.NotificationRules.Name')"
          ></v-text-field>
          <v-select
            v-model="draft.trigger"
            :items="triggers"
            item-title="label"
            item-value="value"
            :label="$t('components.NotificationRules.When')"
          ></v-select>
          <v-text-field
            v-if="draft.trigger === 'silent'"
            v-model.number="draft.threshold_days"
            type="number"
            min="1"
            :label="$t('components.NotificationRules.Days')"
          ></v-text-field>
          <v-text-field
            v-model="draft.webhook_url"
            :label="$t('components.NotificationRules.Webhook')"
            :hint="$t('components.NotificationRules.WebhookHint')"
            persistent-hint
          ></v-text-field>
          <v-text-field
            v-model="draft.email_to"
            class="mt-4"
            :label="$t('components.NotificationRules.Email')"
            :hint="$t('components.NotificationRules.EmailHint')"
            persistent-hint
          ></v-text-field>
          <v-switch
            v-model="draft.enabled"
            color="primary"
            :label="$t('components.NotificationRules.Enabled')"
          ></v-switch>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="dialog = false">
            {{ $t("components.NotificationRules.Cancel") }}
          </v-btn>
          <v-btn color="primary" :loading="saving" @click="save">
            {{ $t("components.NotificationRules.Save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script>
const EMPTY = {
  id: null,
  name: "",
  trigger: "conformity",
  threshold_days: 1,
  webhook_url: "",
  email_to: "",
  enabled: true,
}

export default {
  name: "NotificationRules",
  data() {
    return {
      rules: [],
      dialog: false,
      saving: false,
      testing: null,
      previewing: false,
      previewEvents: null,
      draft: { ...EMPTY },
    }
  },
  computed: {
    triggers() {
      return [
        {
          value: "conformity",
          label: this.$t("components.NotificationRules.TriggerConformity"),
        },
        {
          value: "silent",
          label: this.$t("components.NotificationRules.TriggerSilent"),
        },
      ]
    },
  },
  mounted() {
    this.load()
  },
  methods: {
    describe(rule) {
      if (rule.trigger === "silent") {
        return this.$t("components.NotificationRules.SilentAfter", [
          rule.threshold_days,
        ])
      }
      return this.$t("components.NotificationRules.TriggerConformity")
    },
    channels(rule) {
      let parts = []
      if (rule.webhook_url) parts.push(rule.webhook_url)
      if (rule.email_to) parts.push(rule.email_to)
      return parts.join("  /  ")
    },
    load() {
      this.$http
        .get("api/notifications/")
        .then((response) => {
          this.rules = response.data
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
    },
    open(rule) {
      this.draft = rule ? { ...rule } : { ...EMPTY }
      this.dialog = true
    },
    save() {
      this.saving = true
      let request = this.draft.id
        ? this.$http.put("api/notifications/" + this.draft.id + "/", this.draft)
        : this.$http.post("api/notifications/", this.draft)
      request
        .then(() => {
          this.dialog = false
          this.load()
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
        .then(() => {
          this.saving = false
        })
    },
    remove(rule) {
      this.$http
        .delete("api/notifications/" + rule.id + "/")
        .then(() => this.load())
        .catch((error) => this.$toast.error(this.errorText(error)))
    },
    sendTest(rule) {
      this.testing = rule.id
      this.$http
        .post("api/notifications/" + rule.id + "/test/")
        .then((response) => {
          if (response.data.sent) {
            this.$toast(this.$i18n.t("components.NotificationRules.TestSent"))
          } else {
            this.$toast.error(response.data.errors.join("; "))
          }
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
        .then(() => {
          this.testing = null
        })
    },
    preview() {
      this.previewing = true
      this.$http
        .post("api/notifications/preview/")
        .then((response) => {
          this.previewEvents = response.data.events
        })
        .catch((error) => this.$toast.error(this.errorText(error)))
        .then(() => {
          this.previewing = false
        })
    },
    errorText(error) {
      let data = error.response && error.response.data
      if (data && typeof data === "object" && !data.error && !data.detail) {
        return Object.values(data).flat().join(" ")
      }
      return (data && (data.error || data.detail)) || String(error)
    },
  },
}
</script>
