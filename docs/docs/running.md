# Running Alcali

!!!info
    This page will assume you are running alcali locally.
    
    If you are using docker, just prepend commands with `docker exec -it <name>`

First make sure that Alcali is correctly installed.

You can verify installation by running:

```commandline
alcali current_version
# alcali version 2019.2.2
```

You  can also check that Alcali can access `salt` database and that [needed env var](configuration.md) are set and loaded by running:

```commandline
alcali diagnose
```

It reports the database connection, the required environment variables, the
returner tables and Alcali's own caches. Add `--salt-user <username>` and it
logs in to the Salt API with that user's stored token and exercises each netapi
client in turn, which is what distinguishes a misconfigured `external_auth`
block from a client the master has not enabled.

The same checks are available in the UI under **Settings -> Diagnostics**.

## First Run

### Apply migrations

!!!danger

    **On the first run and after every update, you need to make sure that the database is synchronized with the current set of models and migrations. If unsure, just run `alcali migrate`**


Locally:

```commandline
alcali migrate
```

### Create a super user

Run:

```commandline
alcali createsuperuser
```
You will be prompted for your desired login, email address and password.

## Run

Once migrations are applied and a super user is created, you can start the application.

Alcali use Gunicorn as a WSGI HTTP server. It is installed during the installation process of Alcali.

!!!warning
    If the .env file is not in your current directory, prepend your command with `ENV_PATH=/path/to/env_file`

If you installed Alcali from sources, at the root of the repository, run:

```commandline
gunicorn config.wsgi:application -w 4
```


If you installed Alcali using pip, run:

```commandline
gunicorn config.wsgi:application -w 4 --chdir $(alcali location)
```

In a docker container:
```commandline
docker run --rm -it -p 8000:8000 --env-file=FILE latenighttales/alcali:2019.2.2 bash -c "gunicorn config.wsgi:application -w 4 --chdir $(alcali location)"
```
Where FILE is the location of the [.env file](configuration.md)


## Management commands

Every command below is a Django management command. Where you installed from
sources, run them as `python manage.py <command>` from the repository root;
where you installed the wheel, `manage.py` is not shipped and the `alcali`
console script is the same entry point:

```commandline
alcali <command>
```

!!!warning
    These read the same `.env` as the server. If it is not in the working
    directory, prepend `ENV_PATH=/path/to/directory` - a command that cannot
    find it comes up with no database configured.

    Run them as the user that owns the deployment, not as root, or you will
    leave root-owned files behind. For a packaged install that is typically:

    ```commandline
    sudo -u alcali ENV_PATH=/opt/alcali /opt/alcali/venv/bin/alcali <command>
    ```

| Command | What it does |
| --- | --- |
| `diagnose` | Report the database, environment, returner tables and caches. `--salt-user <name>` also exercises the Salt API and each netapi client. |
| `notify` | Evaluate the notification rules and send what changed. `--dry-run` reports without sending or recording; `--json` emits the events as JSON. Meant for a timer - see [Notifications](configuration.md#notifications). |
| `prune_returns` | Delete returner history older than a window. `--days` is required; `--events-days` sets a separate window for events; `--dry-run` counts without deleting and `--yes` skips the confirmation. The same thing is available in **Settings -> Returner retention**. |
| `manage_token` | Show the Salt API token for a user, or `-r` to revoke and reissue it. |
| `current_version` | Print the installed version. |
| `location` | Print the installed package directory, for `gunicorn --chdir`. |
