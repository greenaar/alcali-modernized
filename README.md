# Alcali (modernized)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

<img align="right" height="300" src="https://upload.wikimedia.org/wikipedia/commons/5/5f/Logo_du_Mois_de_la_contribution_sans_texte.svg">


## What's Alcali?

Alcali is a web based tool for monitoring and administrating **Saltstack**.

## Modernization status

This repository is a fork of Alcali, at `greenaar/alcali-modernized`. It
updates the core application to
Python 3.12, Django 5.2 LTS, Vue 3, Vuetify 3, Node 22 and pnpm. It also replaces the unmaintained `salt-pepper`
client with a small HTTPS client whose certificate verification is enabled by
default.

The self-contained backend suite and production frontend build are expected to
pass in CI. A live deployment must still be tested against the exact Salt
master, REST API and returner database schema used by the operator. LDAP and
Google authentication remain optional compatibility paths and are not part of
the core CI gate.

| Area | Supported baseline |
| --- | --- |
| Python / Django | Python 3.12+, Django 5.2 LTS |
| Frontend | Node 22, Vue 3, Vuetify 3, pnpm 11 |
| Database | SQLite for development; MariaDB/MySQL for Salt returner data |
| Salt API | REST (`rest_cherrypy`), HTTPS verification on by default |

### Local verification

```commandline
python -m venv .venv
.venv/bin/python -m pip install -r requirements/prod.txt -r requirements/test.txt
DB_BACKEND=sqlite3 SECRET_KEY=development-only .venv/bin/python manage.py migrate
DB_BACKEND=sqlite3 SECRET_KEY=development-only .venv/bin/python manage.py runserver
```

In a second terminal:

```commandline
corepack enable
pnpm install --frozen-lockfile --ignore-scripts
pnpm build
```

### Deploying

`docker-compose.prod.yml` runs Alcali against a Salt installation you already
have: the application, a one-shot migration job, and optionally the returner
database. No master, no minion.

```commandline
cp env.prod.sample .env      # then replace every credential
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser
```

Alcali needs two things from Salt, and neither is configured by that stack:
the master must return to the database Alcali reads (`master_job_cache` and
`event_return`), and salt-api must be reachable over HTTPS with an
`external_auth` backend. [docs/docs/docker.md](docs/docs/docker.md) covers the
master-side configuration, the reverse proxy, the supported topologies and
what breaks when each piece is missing.

## Features

- Get notified in real time when a job is created, updated or has returned. 

- Store your jobs results by leveraging the `master_job_store` setting with database master returner.

- Check your minions conformity to their highstate or **any state**.

- Keep track of custom state at a glance.

- Use custom auth module to login into both Alcali and the Salt-api using JWT.

- **LDAP** and **Google OAuth2** authentication.

## Historical demo stack

`docker-compose.yml` is the original all-in-one demo: it runs its own Salt
master and minions so the UI has something to show. It is an integration
fixture, not a deployment - use `docker-compose.prod.yml` for that.

```commandline
git clone https://github.com/greenaar/alcali-modernized.git
cd alcali-modernized
docker compose up --scale minion=2
```


Once you see minions waiting to be approved by the master, you're good to go:

```commandline
...
minion_1  | [ERROR   ] The Salt Master has cached the public key for this node, this salt minion will wait for 10 seconds before attempting to re-authenticate
minion_1  | [INFO    ] Waiting 10 seconds before retry.
...
```

Just connect on [http://127.0.0.1:8000](http://127.0.0.1:8000), login with:

```commandline
username: admin
password: password
```

and follow the [walkthrough](https://alcali.dev/walkthrough/).

## Installation

The easiest way to install it is to use the companion `alcali-formula` Salt
formula, which pins this repository and revision and deploys it as a systemd
service. Read the formula's own README before the first run: it also covers the
Salt returner database and the salt-api/eAuth configuration Alcali depends on.

The upstream [installation](https://alcali.dev/installation/) docs still apply
to everything outside the formula.

## Screenshots

#### Dashboard
![](docs/docs/images/screenshots/dashboard-dark.png)

#### Minion Details
![](docs/docs/images/screenshots/minion-detail-dark.png)

#### Job Details
![](docs/docs/images/screenshots/job-detail.png)

More [here](https://github.com/latenighttales/alcali/blob/2019.2/docs/docs/screenshots.md).

## License

[MIT](LICENSE)

<sub><sub>Image: Jean-Philippe WMFr, derivative work : User:Benoit Rochon [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0)</sub></sub>

## Contributing

If you'd like to contribute, check the [contribute](https://alcali.dev/contribute/)
documentation on how to install a dev environment, then open a pull request
against this repository rather than the original upstream.

There is no CI on pull requests here: day-to-day development happens on a
private Forgejo instance where those pipelines live. Run the checks locally
before opening one - `pytest`, `pytest -m smoke`, `pnpm lint --no-fix src`,
`pnpm test:unit` and `pnpm build`.

Tagged releases *are* built here, by `.github/workflows/release.yml`. It runs
the same checks, builds the frontend, and attaches the wheel and sdist to the
GitHub release. That build step is not optional: `dist/` is untracked, so a
wheel built without it installs cleanly and then serves every UI route as a
500.

And if you like this project, consider donating:

via GitHub Sponsors, or

[![ko-fi](https://www.ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/J3J3173F6)


## Changelog

## [3006.3.0] dev

- int: bugfix and deps update

- feat: i18n (#353)

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

[2019.2.4]: https://github.com/latenighttales/alcali/compare/v2019.2.4...HEAD

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
