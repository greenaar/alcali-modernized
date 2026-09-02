// A starting set of Salt functions for the Run page.
//
// The full list comes from `sys.list_functions` via Settings, which needs a
// working local client - the very thing that is unavailable on a master where
// jobs cannot be collected. Without it the function box offered nothing at
// all, so these are always present and anything the master reports is merged
// over them. The combobox still accepts a function that is not listed.
export const COMMON_FUNCTIONS = {
  local: [
    ["test.ping", "Check that a minion answers"],
    ["test.version", "Salt version on the minion"],
    ["state.apply", "Apply a state, or the highstate with no argument"],
    ["state.highstate", "Apply the highstate"],
    ["state.show_highstate", "Show the highstate without applying it"],
    ["grains.items", "All grains"],
    ["grains.get", "One grain, by key"],
    ["pillar.items", "All pillar data"],
    ["pillar.get", "One pillar value, by key"],
    ["cmd.run", "Run a shell command"],
    ["pkg.list_pkgs", "Installed packages"],
    ["pkg.install", "Install a package"],
    ["pkg.upgrade", "Upgrade packages"],
    ["service.status", "Whether a service is running"],
    ["service.restart", "Restart a service"],
    ["file.stats", "Stat a path"],
    ["disk.usage", "Disk usage"],
    ["network.interfaces", "Network interfaces"],
    ["status.uptime", "Uptime"],
    ["saltutil.sync_all", "Sync modules, states and grains"],
    ["saltutil.refresh_pillar", "Refresh pillar data"],
    ["schedule.list", "Scheduled jobs on the minion"],
  ],
  runner: [
    ["manage.up", "Minions that are responding"],
    ["manage.down", "Minions that are not responding"],
    ["manage.status", "Both, grouped"],
    ["jobs.list_jobs", "Recent jobs from the job cache"],
    ["jobs.lookup_jid", "One job's returns, by jid"],
    ["cache.grains", "Grains the master has cached"],
    ["cache.pillar", "Pillar the master has cached"],
    ["fileserver.update", "Update the file server backends"],
  ],
  wheel: [
    ["key.list_all", "Every key, by status"],
    ["key.accept", "Accept a key"],
    ["key.reject", "Reject a key"],
    ["key.delete", "Delete a key"],
    ["key.finger", "A key's fingerprint"],
  ],
}

/** The built-ins for a client, shaped like the API's own function records. */
export function commonFunctions(client) {
  // local_async and local_batch run the same execution modules as local.
  let kind = client && client.startsWith("local") ? "local" : client
  return (COMMON_FUNCTIONS[kind] || []).map(([name, description]) => ({
    name,
    type: kind,
    description,
    builtin: true,
  }))
}
