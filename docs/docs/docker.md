# Running Alcali in Docker

`docker-compose.prod.yml` runs Alcali as a service you can put in front of an
existing Salt installation. It contains the application, a one-shot migration
job, and — optionally — the database.

It contains no `salt-master` and no `salt-minion`. That is the difference
between it and `docker-compose.yml`, which is the historical all-in-one demo
stack: the demo runs a throwaway Salt installation so the UI has something to
show, and is not something to deploy. If you are looking at a stack with a
`master` service in it, you are looking at the demo.

## What Alcali needs from Salt

Alcali is a read-and-command layer over two interfaces the master exposes. It
does not talk to minions, and it does not use Salt's Python API.

| Interface | What it is | How Alcali uses it |
| --- | --- | --- |
| Returner database | `jids`, `salt_returns`, `salt_events` — written by the master's `master_job_cache` and `event_return` | All job history, event, conformity and dashboard views read these tables directly |
| salt-api | `rest_cherrypy` over HTTPS | Every action: running modules, managing keys and schedules, and authenticating users |

Neither is optional. With the database but no API, Alcali shows history and
can do nothing. With the API but no database, every history view is empty.

Alcali's own tables (users, settings, job templates, custom fields,
conformity) live in that same database, added by `manage.py migrate`. The
three Salt tables above are *unmanaged* Django models: `migrate` never
creates or alters them, because the master owns that schema.

## Topologies

### External database — the normal case

The master already returns to a database. Point Alcali at it and change
nothing on the Salt side except adding salt-api.

```
  Salt master ──returns──▶ MariaDB ◀──reads── Alcali container
       ▲                                          │
       └──────────── salt-api (HTTPS) ────────────┘
```

Leave the `bundled-db` profile off, and set `DB_HOST` to that server.

### Bundled database

This stack owns the database, and the master is reconfigured to return to it.
Only sensible when the master is on the same host as this stack, or on a
trusted network segment — the master's returner connection is plain MySQL
protocol, and `DB_PUBLISH_ADDRESS` defaults to loopback for that reason.

```
  Salt master ──returns──▶ ┌──────────────────────────┐
       ▲                   │  db (MariaDB)            │
       │                   │   ▲                      │
       │                   │   └─reads── web (Alcali) │
       └──── salt-api ─────┼──────────────┘           │
                           └──────────────────────────┘
```

Enable it with `--profile bundled-db` and set `DB_HOST=db`.

!!!warning

    The bundled database is where your entire job history lives. It is in the
    `db-data` named volume. `docker compose down -v` deletes it. Back it up
    like any other database, and pin `ALCALI_DB_IMAGE` so a MariaDB major
    version does not change under you on the next `pull`.

## Configuring the Salt master

Nothing in the compose stack configures Salt. Do this on the master, in a file
under `/etc/salt/master.d/`.

!!!note

    The [alcali-formula](https://forge.thatserver.ca/salt/alcali-formula) writes
    exactly this file for you, and can do so for a containerised Alcali it does
    not otherwise manage — see its `deploy:method: docker` and
    `deploy:method: external` modes. Use it if the master is already
    Salt-managed; the rest of this section is what it produces.

```yaml
# /etc/salt/master.d/alcali.conf

# Job history. Both are required: master_job_cache fills salt_returns and
# jids, event_return fills salt_events.
master_job_cache: mysql
event_return:
  - mysql

# How long the master keeps job data. Alcali cannot show what has been pruned.
keep_jobs_seconds: 604800

mysql.host: '127.0.0.1'
mysql.port: 3306
mysql.db: 'salt'
mysql.user: 'alcali'
mysql.pass: 'the DB_PASS value from .env'

rest_cherrypy:
  host: 0.0.0.0
  port: 8080
  ssl_crt: /etc/salt/pki/api.crt
  ssl_key: /etc/salt/pki/api.key
  debug: false

# Salt 3006+ refuses every netapi client unless it is listed here.
netapi_enable_clients:
  - local
  - local_async
  - runner
  - runner_async
  - wheel
  - wheel_async

# Required for SALT_AUTH=rest: the master calls back to Alcali to verify the
# credentials a user logged in with, so Alcali's accounts are the source of
# truth and there is no second user directory to keep in sync.
keep_acl_in_token: true
external_auth:
  rest:
    ^url: http://127.0.0.1:8000/api/token/verify/
    admin:
      - '.*'
      - '@runner'
      - '@wheel'
      - '@jobs'
```

The master needs the database connector in *its* Python, which for onedir
packages is not the system one:

```bash
/opt/saltstack/salt/bin/pip3 install mysqlclient
```

Restart `salt-master` and `salt-api` after writing the file.

### The `^url` callback is a loop back into this stack

With `SALT_AUTH=rest`, a login goes: browser → Alcali → salt-api →
`^url` → Alcali. The master must be able to reach the address in `^url`. If
Alcali is only published on loopback and the master is on the same host,
`http://127.0.0.1:8000/api/token/verify/` works. If they are on different
hosts, that URL has to be the reverse proxy's HTTPS address, and the master
has to trust its certificate.

Getting this wrong produces a login that fails with no error in Alcali's log,
because the failure happens inside the master. Check the master log first.

## Deploying

```bash
cp env.prod.sample .env
```

Fill in `.env`. At minimum: `SECRET_KEY`, `DB_*`, `ALLOWED_HOSTS`, `SALT_URL`.
Then:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Create the first account — there is no default admin in this stack, unlike the
demo:

```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser
```

Confirm the wiring before pointing users at it. `diagnose` reports the
database connection and any unset required variable, and exits non-zero if
either is wrong:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py diagnose
```

Then log in and use **Settings → Refresh modules**, which calls
`sys.list_functions` on `MASTER_MINION_ID` through salt-api. If that works,
both interfaces are live.

## Reverse proxy

The `web` service publishes to `127.0.0.1:8000` and speaks plain HTTP.
gunicorn is not a TLS terminator, does not rate-limit, and does not defend
against slow-client attacks. Terminate TLS in front of it.

```nginx
server {
    listen 443 ssl;
    server_name alcali.example.com;

    ssl_certificate     /etc/ssl/alcali.crt;
    ssl_certificate_key /etc/ssl/alcali.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        # Django trusts this header (SECURE_PROXY_SSL_HEADER). Set it here so
        # a client-supplied copy is always overwritten.
        proxy_set_header X-Forwarded-Proto $scheme;

        # The events view is a Server-Sent Events stream. Without these it
        # buffers until the connection times out and events never appear.
        proxy_buffering off;
        proxy_read_timeout 24h;
    }
}
```

Then set in `.env`:

```
SECURE_SSL_REDIRECT=true
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
CSRF_TRUSTED_ORIGINS=https://alcali.example.com
ALLOWED_HOSTS=alcali.example.com
```

`CSRF_TRUSTED_ORIGINS` is the one most often missed. Without it every POST
from the UI is rejected with a CSRF failure, which looks like a broken login
rather than a configuration problem.

## Salt's TLS certificate

`SALT_VERIFY_TLS` defaults to true, and Alcali forwards user credentials to
salt-api, so leave it on. When the master uses an internal CA, mount the CA
bundle rather than disabling verification:

```yaml
volumes:
  alcali-tls:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /etc/ssl/salt   # containing salt-ca.pem
```

```
SALT_CA_BUNDLE=/etc/alcali/tls/salt-ca.pem
```

A self-signed certificate on the master works the same way: point
`SALT_CA_BUNDLE` at the certificate itself.

## Upgrading

```bash
# Pin the new version in .env first, then:
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

`up -d` reruns the `migrate` job to completion before restarting `web`, so
schema changes never race between gunicorn workers. Back up the database
first; there is no downgrade path for Django migrations.

## Operational notes

- **Sizing.** `docker/gunicorn_config.py` sets three sync workers. The events
  view holds a worker for the life of the SSE stream, so a sync worker pool
  is consumed by concurrent viewers. Raise `workers` before adding users.
- **Log output.** Both services log to stdout; use `docker compose logs`, or
  configure a logging driver. Nothing writes to a file inside the container.
- **The migrate job stays in `docker compose ps -a`** with exit code 0. That
  is normal for a one-shot service.
- **`db` publishes a port even on loopback.** If the master is elsewhere and
  you widen `DB_PUBLISH_ADDRESS`, put the connection on a private network or
  enable TLS on MariaDB. Returner traffic contains full job output.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Job list empty, everything else works | Master is not returning to this database. Check `master_job_cache` and the connector in the master's Python. |
| Events view empty, jobs populate | `event_return` not set — it is separate from `master_job_cache`. |
| Login fails, no error in Alcali's log | The `^url` callback. The master cannot reach Alcali's verify endpoint. Check the master's log. |
| CSRF failure on every POST | `CSRF_TRUSTED_ORIGINS` missing the proxy's origin. |
| `migrate` exits non-zero on first run | Database unreachable or credentials wrong; `docker compose logs migrate` has the connection error. |
| Warning about missing Salt returner tables | The database has Alcali's tables but not Salt's. With an external database that means `DB_NAME` points at the wrong schema. |
| `SSLCertVerificationError` reaching salt-api | Internal CA not trusted — set `SALT_CA_BUNDLE`, do not turn off `SALT_VERIFY_TLS`. |
