# Changelog

## [3008.6.0] - 2026-09-02

### Added

- Returner retention in the UI. Settings gains a staff-only card that reports
  how many rows fall outside a window before removing anything, and deletes
  only on confirmation. Salt's mysql returner never removes rows of its own -
  `keep_jobs_seconds` governs the master's job cache, not this database - so
  these tables grow for the life of the installation. `GET`/`POST /api/prune/`
  back it, and a removal is written to the audit log.

### Fixed

- Card headers laid their controls out vertically: the Minions "Column" button
  sat above the search field rather than beside it, and the same applied to
  every other card with a header control. `v-card-title` was a flex row in
  Vuetify 2 and is a block in Vuetify 3, so the `v-spacer` in those headers did
  nothing.

## [3008.5.2] - 2026-09-02

### Added

- `manage.py alcali_check` reports whether the master is writing its job cache.
  `master_job_cache` writes the publish payload to `jids` and the returner
  writes results to `salt_returns`; those are separate writes, and only the
  first is what the master reads back when collecting a job's returns. When
  `jids` stops being written the master logs `jid does not exist` and abandons
  the job, so every Salt-backed action returns an empty result with no error -
  a refresh that reports success and populates nothing. The check flags a
  recent job present in `salt_returns` but absent from `jids`.

### Fixed

- Refreshing minions reported "0 minions refreshed" as a success when the
  master answered with nobody at all. That is not an empty fleet, it is a
  master that could not read its own job back, and the two looked identical.

## [3008.5.1] - 2026-09-02

### Fixed

- The frontend smoke tests timed out in CI while passing locally. They waited
  for `networkidle`, and the frontend holds an event stream open and reconnects
  on a backoff for as long as the page is open, so the network never reliably
  goes quiet - whether the wait returns is a race between that backoff and
  Playwright's 500ms idle window. It is won on a machine where the unreachable
  master refuses the connection instantly and lost on one where that connection
  hangs. Navigation now waits for the application shell, which is what the
  assertions actually need. The smoke fixture also points at a closed port with
  a short timeout, so an unreachable master cannot cost 30 seconds a request
  whatever the runner's networking does.

## [3008.5.0] - 2026-09-02

### Fixed

- Every navigation icon sat above its label rather than beside it. The
  `v-list-item-content`, `-action` and `-avatar` wrappers those items nested
  are Vue 2 components; the migration kept them alive as shims that render a
  plain `div`, and a div is block level. The lists use Vuetify 3's own
  `v-list-item` now, and the shims are gone.

- Twenty-nine `text`, `small`, `tile` and `dark` props on buttons and chips
  were Vuetify 2 spellings that Vuetify 3 ignores, so everything meant to be a
  quiet text button rendered as a full-size filled block.

- The minions table put four labelled buttons in the actions column, which
  wrapped one per line and made every row four rows tall. They are icon
  buttons with tooltips in a column wide enough to hold them.

- The keys card on the overview was a twelfth of the width, which clipped the
  counts off its right edge, and the jobs search hint was cut off mid-word.

- Button labels were a mix of `detail`, `run job` and `Refresh`. Vuetify 2
  upper-cased them all, which hid it; they are consistently title case now.
  `Actions` and `Run on` were hard-coded English and are translated.

- Certificate verification against a loopback salt-api. salt-api generally
  serves the certificate for the master's public name, which cannot match
  127.0.0.1, so verification fails on an address mismatch while proving
  nothing - the traffic never leaves the host. With `SALT_VERIFY_TLS` unset,
  a real host is still verified and loopback is not; setting it forces either
  behaviour, and `SALT_CA_BUNDLE` still wins over both.

### Changed

- The theme defines its grounds rather than only `primary` and `secondary`, so
  cards sit on a page background instead of white on white, and the bars follow
  the theme rather than being hard-coded black. Cards, buttons, fields and
  chips take their radius and density from one place.

## [3008.4.2] - 2026-09-02

### Fixed

- The Salt websocket indicator claimed a healthy connection to a master it had
  never reached, and could not report one going away. `get_events` returned a
  dict on failure, which `StreamingHttpResponse` iterated as its keys, so the
  endpoint streamed the word "error" with a 200. It answers 503 now, and the
  client acts on both the open and the error, so the indicator no longer waits
  for a page reload to tell the truth.

- Column headers did not sort the States and Audit tables. `LegacyDataTable`
  derived the sort purely from its prop, so a caller passing a plain `sort-by`
  rather than binding it got header clicks that emitted an update nobody
  listened to and a table that re-rendered in its original order. It keeps the
  sort itself when the prop is not bound, and still yields to a caller that
  does bind it.

- The Run page controls did not fit their row: several sat in one-twelfth-wide
  columns with offsets between them, so "Client Type", "Async", "Batch",
  "Timeout" and "Target Type" wrapped inside their own boxes. The two rows use
  even, responsive widths and no offsets, since the columns appear and
  disappear with the client type.

- An event whose `data` column could not be parsed rendered as `{}`, which was
  indistinguishable from an event that genuinely carried nothing. The expansion
  now shows the column as stored, and says which case it is.

### Added

- `alcali_check --salt-user` names the two failures that account for almost
  every empty page: an `external_auth` block on the master with no section for
  the eauth Alcali logs in with, and a `netapi_enable_clients` list missing the
  client a page needs. It prints the config the master requires, and probes the
  wheel and local clients separately so the report says which page each failure
  affects.

## [3008.4.1] - 2026-09-01

### Fixed

- Job output was black on black under the default light theme. ansi2html was
  emitting its colours as CSS classes in a `<style>` block, which the sanitiser
  drops, so the text fell back to the inherited colour on a hard-coded black
  panel - invisible in light mode, uncoloured in dark. The converters now emit
  inline styles, which survive sanitising, and the panel sets its own
  foreground so unstyled output can never be unreadable.

- Succeeding jobs were reported as failed. 3008.2.1 changed the fallback for a
  payload that does not state its own success to read `salt_returns.success` -
  but the returner writes that column as `ret.get("success", False)`, so a
  false there means either "it failed" or "the payload never said". The verdict
  now comes from the state results when a highstate is being judged, then
  retcode, and is reported as unknown - a grey chip rather than a red one -
  when nothing in the record actually says. An affirmative success column still
  counts; a false one no longer condemns a job on its own.

- Refreshing minions reported success when it had failed. `run_raw` signals a
  failure by returning `{"error": ...}`, which the refresh-everything path
  treated as a minion list: an unreachable master produced an empty list, a
  200, and a cheerful "0 minions refreshed", leaving the Minions, Keys and
  Schedules pages empty with nothing at all explaining why.

- The Salt-delegated minion actions were exempted from the staff-only write
  rule added in 3008.3.0 with an empty permission list, which in DRF means no
  permission class runs at all - so `silent`, `conformity`, `preview_target`
  and `refresh_minions` were reachable without logging in. They require
  authentication again.

### Added

- `manage.py alcali_check` now reports how many rows each of Alcali's own
  caches holds and what fills each one, since an empty Minions page looks
  exactly like a fleet with no minions. `--salt-user <name>` performs the same
  API login the application does, using that user's stored token, and reports
  what actually happens - unreachable host, TLS failure, rejected credentials,
  or a login that succeeds but grants no permissions.

## [3008.4.0] - 2026-09-01

Features built on data the Salt returner was already storing and Alcali was
not reading.

### Added

- **Minions that stopped reporting.** A minion that goes quiet writes nothing
  to `salt_returns`, so it appeared in no view and looked like a healthy one.
  The accepted keys are the roster: `/api/minions/silent/` compares them
  against each minion's most recent return and separates "never returned" from
  "stale". Shown on the overview with a selectable window.

- **Jobs nothing answered.** `salt_returns` only gets a row from a minion that
  replied, so a job that timed out on part of its targets looked complete. The
  `salt/job/<jid>/new` event holds the roster the master expected, which is the
  only record of the ones that never replied; `/api/jobs/<jid>/summary/`
  reconciles the two and the per-jid view leads with the discrepancy. A missing
  `new` event is reported as an unknown roster rather than as "nothing missing".

- **State cost and drift.** Every state in a highstate return carries
  `duration`, `__sls__` and `__id__`, all of which were being discarded.
  `/api/states/durations/` aggregates them over a window - total, mean and
  worst time per state, how many minions run it, and the share of runs that
  reported changes. A state changing on nearly every run is being re-applied
  rather than converging, which a conformity boolean cannot show.

- **Blast-radius preview.** The Run page shows how many known minions a target
  expression selects, evaluated from stored grains and pillar. Compound, pcre,
  range and nodegroup expressions are reported as not evaluated rather than
  approximated - a wrong blast radius is worse than none.

- **Search that finds minions by their grains.** The global search now matches
  inside the stored grains and pillar, so a minion can be found by address, MAC
  or kernel version.

- **Audit log.** Changes to Alcali's own records - minions, conformity rules,
  custom fields, job templates, users, tokens, key actions - left no trace
  anywhere, since they never reach Salt. They are recorded with the acting user
  and shown to staff on the users page. Writing an entry can never fail the
  action it describes.

- **Job filters for function and status**, answered in SQL, plus the target
  expression, submitting user and Salt job metadata from `jids.load` on the job
  summary. That load also carries the master publish key and sometimes an eauth
  token, so the response is built from an allowlist.

- **`manage.py prune_returns --days N`** trims the returner tables, which the
  mysql returner never does. Separate window for `salt_events`, orphaned `jids`
  removed, dry run by default.

### Changed

- The jobs list no longer serialises `return` and `full_ret` - the entire job
  payload, and nothing rendered either.
- `alcali_check` reports returner indexes Alcali sorts on that Salt's schema
  does not create; `docs/returner-indexes.sql` adds them to an existing
  database.
- The jobs and events search boxes say how many loaded rows they filter, rather
  than looking like they search all history.
- The test database builds the returner tables from Salt's own DDL. Building
  them from the models made `salt_returns.id` UNIQUE, which no real deployment
  is, hiding anything that assumed one row per minion.

## [3008.3.0] - 2026-09-01

### Security

- **Any signed-in user could read and overwrite every other user's Salt token.**
  `UserSettingsViewSet` had no permission class and no queryset filter, and its
  serializer exposed `token` — the credential Alcali authenticates to the master
  with. `GET /api/userssettings/` returned every user's token, and a PATCH could
  replace one. Settings are now scoped to the requesting user, and `token` is
  read-only there (the token endpoints still manage it).

- Alcali's own records could be changed by any signed-in user. Minions,
  conformity rules, minion custom fields and job templates now require staff to
  modify and stay readable to everyone. Actions delegated to the master
  (running a job, refreshing minions, managing keys and schedules) are
  unchanged: salt-api applies the caller's own eauth ACL to those.

- `SECRET_KEY` no longer falls back to a value published in this repository.
  It signs the JWTs, so a deployment that fell back to it could have its tokens
  forged. Alcali now refuses to start without one unless `DJANGO_DEBUG` is set.

- The Salt token comparison in the eauth `verify` endpoint is now constant time.

### Fixed

- The Run page could not run anything, and per-minion Refresh refreshed every
  minion. The frontend sends JSON, while thirteen view sites read
  `request.POST`, which is only populated for form bodies: `POST /api/run/`
  returned 500 and `refresh_minions` silently took the refresh-everything
  branch. All of them now read `request.data`.

- `run` and `verify` returned `None` on some paths, which DRF turns into a 500.

- A job whose payload said nothing about success was reported as succeeded:
  `success_bool` fell back to returning the jid, a non-empty string that a
  BooleanField serialises as true. It now falls back to the returner's own
  success column.

- The jobs list issued one query per row against the returner database
  (`SaltReturns.user()` fetching a jids row each time), so the 1000-row option
  cost about a thousand round trips. It is now two queries regardless of size;
  `jobs_filters` no longer instantiates every jids row, and `last_highstate` is
  memoised so the minions and conformity views stop computing it twice.

- The events table was hard-capped at 50 rows with nothing saying so. The
  window is now settable with `?limit=` (default 100, max 1000), the total is
  returned in `X-Total-Count`, and the table says how many of how many it shows.

- A near-expired refresh token produced a malformed request instead of a clean
  redirect: the interceptor returned the router's promise where axios wanted a
  request config.

### Changed

- `dist/` is no longer tracked. It is build output; keeping it in the tree made
  every frontend change carry a large generated diff and let the shipped bundle
  drift from `src/`. The container already built it from source, and the release
  workflow now does too, so the wheel is built from the tag's sources.

- CI runs the frontend lint, the frontend unit tests, and a browser smoke test
  that loads every route against the built bundle and fails on any console
  error. Every defect fixed in 3008.2.1 compiled cleanly and only showed up in
  a browser. Run it locally with `pnpm build && pytest -m smoke`.

- `pnpm test:unit` runs the Jest suite that had been sitting in the tree with no
  runner configured.

## [3008.2.1] - 2026-09-01

Fixes for the Vue 3 / Vuetify 3 migration: several Vue 2 and Vuetify 2 APIs had
been left in place, where they are silently ignored rather than failing loudly.

- fix: every API call was addressed relatively, so on a nested route such as
  `/jobs/<jid>/<id>` it resolved to `/jobs/<jid>/api/...` and 404'd. Job detail
  and minion detail showed an empty record and a failed status

- fix: no server-side route served the SPA shell, so a refresh or a direct link
  to anything but `/` returned a Django 404

- fix: the settings store started empty while every table read nested paths out
  of it, which aborted `Layout`'s created hook

- fix: `v-select` items shaped `{text, value}` rendered as `[object Object]` on
  the overview (Filter, Period) and the run page (Client Type, Target Type);
  `item-text` was renamed `item-title` in Vuetify 3, leaving the settings page
  target, functions and language dropdowns empty

- fix: the refresh speed dial rendered unpositioned and its actions were
  unreachable, so minions, keys and schedules could not be refreshed from the UI

- fix: the conformity chart never drew — a `ref` in `v-for` is an array in
  Vue 3, and the canvas is a `v-menu` activator, so the ref never resolved

- fix: events could not be expanded (`expanded-item` is `expanded-row` in
  Vuetify 3), and one malformed row blanked the whole table

- fix: creating a user returned 500, because the serializer deleted fields a
  JSON request never sends

- fix: conformity detail crashed rendering, `$t()` having been handed a boolean

- fix: `v-tabs-slider`, `v-expansion-panel-header`, Vue 2 filters, `.native`
  and `beforeDestroy` removed; `.sync` replaced with `v-model` arguments, so
  table sort and page-size preferences persist again

- fix: both search boxes on the search page were inert

- fix: missing `views.JobDetail.failed` and `views.Search.Jobs` translations,
  and a `MinionDetail.Refreshing` key with a trailing space

- int: ESLint moved to the Vue 3 preset, which is what surfaced the remaining
  Vue 2 constructs

## [3008.2.0] - 2026-08-19

First release from the Forgejo fork.

- int: Python 3.12, Django 5.2 LTS, Vue 3, Vuetify 3, Node 22, pnpm 11

- int: replaced the unmaintained salt-pepper client with an HTTPS client that
  verifies certificates by default

- int: CI, docs and release pipelines moved to Forgejo Actions

- fix: container image could not build (the eslint ignore list never reached
  the frontend stage) and could not start (CRLF, non-executable entrypoint)

- fix: test suite migrated the development database and passed only once per
  checkout

- fix: sdist omitted `requirements/`, and `pyproject.toml` was not valid TOML,
  so no PEP 517 build succeeded

- fix: frontend advisories in dompurify, js-yaml, nanoid and fast-uri

## [3003.1.0] - 2021-04-23

- int: updated deps (#317)

- fix: py36 compatible (#306)

- fix: non-standard-minion-response (#281)

- int: offline version (#225)

[3003.1.0]: https://github.com/latenighttales/alcali/compare/v3003.1.0...HEAD

## [3000.1.0] - 2020-04-26

- use salt 3000

- updated deps (#185)

- fix: UI errors (#187)

- fix: users are able to reset their pw (#184)

- fix: responsive layout (#178)

[3000.1.0]: https://github.com/latenighttales/alcali/compare/v2019.2.5...HEAD

## [2019.2.4] - 2020-02-14

- fix: password update (#164)

- update deps 20200207 (#155)

- fix: Less restrictive minion_id regex and error mgmt (#140)

[2019.2.4]: https://github.com/latenighttales/alcali/compare/v2019.2.4...v2019.2.5

## [2019.2.3] - 2019-12-10

- feat: Google OAuth2 (#130)

- updated deps (#111)

- feat: Group jobs by jid (#106)

- int: error mgmt (#105)

- fix: favicon and boolrepr (#102)

- fix: removed useless icon files, fixed boolean repr (#100)

- fix: state render,Layout removed admin

- feat: predefined jobs (#98)

- fix: Boolean repr (#97)

- feat: LDAP auth backend (#84)

- fix: async run, updated deps (#82)

- feat: fold/unfold all

- feat: display current version in gui and cli dynamically (#76)

- fix: timezone, success bool for custom modules (#75)

- async link: resolve #69 (#74)

- feat: schedule disable/enable (#72)

- fix: schedules, keys, updated vuetify (#71)

- int: updated docs, added contribute section, screenshots (#62)

[2019.2.3]: https://github.com/latenighttales/alcali/compare/v2019.2.3...v2019.2.4

## [2019.2.2] - 2019-09-21

- use slim docker image

- Added rest auth

- Added pillar override

- Updated deps

[2019.2.2]: https://github.com/latenighttales/alcali/compare/v2019.2.2...v2019.2.3

## [2019.2.1] - 2019-09-21

- Frontend refactor

[2019.2.1]: https://github.com/latenighttales/alcali/compare/v2019.2.1...v2019.2.2
