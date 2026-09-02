// Mirror of api/migrations/usersettings.json.
//
// Every table and card reads deep paths out of `store.state.settings`
// (`settings.MinionsTable.table.sortBy` and friends). The server copy only
// arrives after `fetchSettings` resolves, so the store has to start from this
// shape or those reads throw while the request is in flight.
export default function defaultSettings() {
  return {
    Layout: { mini: false, drawer: true, dark: false },
    Home: { JobsChartCard: { filter: "all", period: 7 } },
    MinionsTable: {
      table: {
        columns: [
          "minion_id",
          "conformity",
          "fqdn",
          "os",
          "oscodename",
          "kernelrelease",
          "last_job",
          "last_highstate",
        ],
        itemsPerPage: 10,
        sortBy: "minion_id",
        sortDesc: false,
      },
    },
    MinionDetail: {
      InfosCard: { tab: "common" },
      NetworkCard: { tab: "interface" },
      MinionDetailCard: { tab: "grain" },
    },
    JobsTable: { table: { itemsPerPage: 10, sortBy: "jid", sortDesc: true } },
    RunCard: { tab: "formatted" },
    JobTemplatesTable: { table: { itemsPerPage: 10, sortBy: "name", sortDesc: false } },
    ScheduleTable: { table: { itemsPerPage: 10, sortBy: "name", sortDesc: false } },
    ConformityTable: { table: { itemsPerPage: 10, sortBy: "minion_id", sortDesc: false } },
    KeysTable: { table: { itemsPerPage: 10, sortBy: "minion_id", sortDesc: false } },
    EventsTable: { table: { itemsPerPage: 10, sortBy: "alter_time", sortDesc: true } },
    UserCard: { table: { itemsPerPage: 10, sortBy: "username", sortDesc: false } },
    UserSettings: {
      notifs: { created: true, published: true, returned: true, event: false },
      max_notifs: 15,
    },
    selected_master: "",
    language: "en",
  }
}

// Server settings may predate a key added since the row was written, so merge
// onto the defaults rather than replacing them.
export function mergeSettings(defaults, stored) {
  if (!stored || typeof stored !== "object" || Array.isArray(stored)) return defaults
  const merged = { ...defaults }
  Object.keys(stored).forEach(key => {
    const base = defaults[key]
    const value = stored[key]
    if (base && typeof base === "object" && !Array.isArray(base)) {
      merged[key] = mergeSettings(base, value)
    } else {
      merged[key] = value
    }
  })
  return merged
}
