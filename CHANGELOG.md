# Changelog

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
