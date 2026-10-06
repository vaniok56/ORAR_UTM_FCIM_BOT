# 🤖 ORAR UTM FCIM BOT

## 📋 Table of Contents
- [Introduction](#-introduction)
- [Prerequisites](#️-prerequisites)
- [Setup and First Run](#-setup-and-first-run)
- [Configuration Details](#️-configuration-details)
- [Schedule File Format](#️-schedule-file-format)
- [Managing the Bot](#️-managing-the-bot)
- [Troubleshooting](#-troubleshooting)

## ✨ Introduction

Telegram bot for UTM FCIM schedules by day or week, class reminders, and
reviewed schedule uploads. This guide covers Docker setup on Linux and macOS.

## 🛠️ Prerequisites

- [Docker](https://docs.docker.com/engine/install/) with
  [Docker Compose](https://docs.docker.com/compose/install/).
- [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).
- A Telegram bot token from [BotFather](https://t.me/BotFather) and API
  credentials from [my.telegram.org](https://my.telegram.org).
- At least one valid schedule workbook. An example is provided in
  `schedules/orar_example.xlsx`; real faculty schedules are not included.

The bot connects to Telegram outbound. It needs no inbound port or router rule.
The supplied `docker-compose.yml` publishes MySQL on port 3306. For an
internal-only database, remove its `mysql.ports` block before the first run.
Changes to an existing deployment's bindings require separate review and approval.

## 🚀 Setup and First Run

These steps are for a new installation. For an existing bot, use
[Updating the bot](#updating-the-bot); do not overwrite its configuration or data.
Obtain approval before container or database changes on a managed host.

### 1. Clone the repository

```sh
git clone https://github.com/vaniok56/ORAR_UTM_FCIM_BOT.git
cd ORAR_UTM_FCIM_BOT
```

Use the intended release branch or commit. Run the following commands from
the repository root.

### 2. Create configuration and contributors files

```sh
umask 077
cp configs/config.ini.template configs/config.ini
cp configs/mysql.env.template configs/mysql.env
cp contributors.csv.template contributors.csv
chmod 600 configs/config.ini configs/mysql.env contributors.csv
```

Fill in the configuration files using [Configuration Details](#️-configuration-details).
Remove the template's example contributor rows; keep its `user_id,orar` header.
Add rows only for users allowed to update the corresponding study year.

If you will own this installation, set `main_admin` in
`src/handlers/admin_handlers.py` to your `U`-prefixed Telegram ID before building.
Owner-only commands use this ID, independently of database admin rank.

### 3. Prepare database initialization

```sh
cp init/init.sql.template init/init.sql
chmod 600 init/init.sql
```

Edit the `your_user` and `your_password` placeholders in `init/init.sql` to match
`MYSQL_USER` and `MYSQL_PASSWORD` in `configs/mysql.env`. Escape SQL string
literals correctly. Review the initial `current_year` value for your deployment.
Keep generated SQL private; do not paste credentials into shell commands or Git.

MySQL runs initialization scripts only when its data directory is empty.
Changing `init.sql` does not migrate an existing database. Bot startup does not
create or alter database tables.

### 4. Add schedules and writable directories

```sh
mkdir -p schedules sessions logs backups
chmod 700 sessions logs backups
```

Place runtime workbooks at `schedules/orar1.xlsx` through `orar4.xlsx`, using the
format below. For a local demonstration, copy `schedules/orar_example.xlsx` to
`schedules/orar1.xlsx`. Do not use the example as a production schedule.

At least one year must contain valid group headers. Missing years stay inactive.
Provide `contributors.csv` and schedules before startup; the bot reads them and
generates `src/dynamic_group_lists.py` before connecting to Telegram.

### 5. Start MySQL and the bot

```sh
docker compose up -d mysql
docker compose up -d --build orar_bot
docker compose ps
docker compose logs --tail 80 -f orar_bot
```

MySQL should become healthy before the bot starts. Look for successful database
and Telegram connections, then send `/start` and request a schedule in Telegram.
Ctrl+C stops log following, not the running container.

These commands start only MySQL and the bot. The optional `restarter` service
is not needed to run the bot.

### 6. Grant admin access

Send `/start` first so your user record exists. Open MySQL with an interactive
password prompt; enter the configured root password without putting it in arguments:

```sh
docker compose exec mysql mysql -uroot -p orar_bot
```

Replace `U<YOUR_TELEGRAM_ID>` below with your actual sender ID:

```sql
UPDATE settings s JOIN users u ON u.id = s.id
SET s.admins = 1 WHERE u.SENDER = 'U<YOUR_TELEGRAM_ID>';

SELECT u.SENDER, s.admins FROM users u JOIN settings s ON s.id = u.id
WHERE u.SENDER = 'U<YOUR_TELEGRAM_ID>';
```

Exit MySQL, then reload the bot's startup admin list:

```sh
docker compose restart orar_bot
```

Check `/admin_help`. Do not restart MySQL for this change.

## ⚙️ Configuration Details

| File or setting | Purpose |
| --- | --- |
| `configs/config.ini` | `[default]` section with `api_id`, `api_hash`, `BOT_TOKEN`. |
| `configs/mysql.env` | `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`. Initialization SQL uses database name `orar_bot`. |
| `configs/my.cnf` | MySQL configuration shipped with the repository. |
| `contributors.csv` | `user_id,orar` entries granting upload access to study years 1–4. |
| `ORAR_CONFIG` | Configuration path; defaults to `configs/config.ini`. Mounted read-only. |
| `ORAR_SESSION` | Telegram session path; defaults to `sessions/session_master`. |
| `app_settings.current_year` | Cohort-year setting used by group/year logic, separate from study year 1–4. |

Keep generated config and SQL files `0600`. Never commit credentials or sessions.
Production MySQL data uses the bind mount `./mysql:/var/lib/mysql`.

## 🗓️ Schedule File Format

Runtime files are `schedules/orar<study_year>.xlsx`, where study year is 1–4.
Follow `schedules/orar_example.xlsx`:

- The bot reads the first worksheet. The example uses `Table 2`.
- Cell A1 contains the schedule version.
- Row 1 contains group names from column C, such as `TI-241`.
- Column A contains weekdays; column B contains class time intervals.
- Group columns contain subject, teacher, and room text. Preserve the example's
  paired rows and merged-cell layout for alternating weeks.

These are runtime workbooks, not raw dean exports. Use the upload workflow below
to convert and review dean-layout files. Publication also saves a hash-matched
`orarN.classifications.json`. Without a matching sidecar, class text stays raw.

## 🕹️ Managing the Bot

### Status, logs, and stopping

```sh
docker compose ps
docker compose logs --tail 80 orar_bot
docker compose stop orar_bot
docker compose start orar_bot
```

Stop only the bot when maintaining its code. Preserve `mysql/`, `sessions/`,
schedules/sidecars, contributors, and backups. Do not reset a database to upgrade.

### Updating the bot

Before updating, review the release, confirm any required manual database changes,
back up affected files and database, and retain the previous source/image.
Prepare a full database backup including routines with an authorized account;
the bot's automated dump does not include routines. Test restoration separately.

Production bind-mounts `src/`, so stop the bot before replacing source files.
After approval, update the intended branch and recreate only the bot:

```sh
docker compose stop orar_bot
git pull --ff-only
docker compose build orar_bot
docker compose up -d --no-deps orar_bot
docker compose logs --tail 80 orar_bot
```

Do not proceed if checkout/build fails. Restore previous source/image instead.
Leave MySQL running. Verify schedules, reminder delivery, mounts, and startup
before declaring the update complete. Do not copy test config or data into production.

### Uploading schedules

1. Send `/update_schedule` as owner or authorized contributor.
2. Send one dean XLSX and optional matching PDF per study year, up to eight files
   total. XLSX limit is 20 MiB; PDF limit is 30 MiB. Order and Telegram albums are supported.
3. If a version cannot be read from the PDF filename, send a value such as `2=3`
   or `2=final`, then tap **Review uploads**. Numeric versions are 1–99.
4. Read each year's audit/diff reports, then tap its Publish button. No automatic
   publication occurs; years publish independently.

File titles must agree on academic year, study year, and semester. PDF alone
cannot publish. Manual versions override filename guesses with a warning.
Same/older revisions and PDF findings require explicit review; parser/layout/
source-output failures block publication. Sunday/seven-day layouts are unsupported.

Batches expire after 30 minutes idle. Accepted files/versions and valid review/
publish actions refresh expiry. Duplicate files require a new batch; editing ends
once review is prepared. Stale targets or failed publication clear remaining items,
but already-published years stay committed.

Review CSV includes source coordinates and XLSX hash; changed-cell CSV uses
ISO-even/ISO-odd weeks. Previous workbook, sidecar, and group catalog copies
remain in `schedules/rollback/`. Check schedules and reminders after publication.

### Replacing runtime workbooks manually

Legacy runtime XLSX files cannot be uploaded through the new bot workflow. To
install one manually, back up its workbook and sidecar, stop only the bot, replace
`schedules/orarN.xlsx`, then start the bot. A running process caches its workbooks;
copying a file alone does not reload it.

Keep a sidecar only when its workbook hash matches. A mismatched sidecar is ignored
and original class text is displayed. Do not replace production files with test
copies or overwrite source-review decisions without approval.

### Local test bot

Use `docker-compose.test.yml` with project `orar_test`, `configs/config2.ini`,
and `.test-env/`. It uses a separate named MySQL volume and publishes no ports.
Mac and reactor stage share the test token; never run both simultaneously.

Prepare `config2.ini` from the Telegram config template and use test credentials.
Prepare current initialization SQL as in first-run setup. For an existing test
database, apply needed schema changes manually; initialization will not rerun.

```sh
mkdir -p .test-env/{schedules,sessions,logs,backups}
chmod 700 .test-env .test-env/{schedules,sessions,logs,backups}
cp -p schedules/orar[1-4].xlsx .test-env/schedules/
cp -p contributors.csv .test-env/contributors.csv
chmod 600 configs/config2.ini configs/mysql.env .test-env/contributors.csv
docker compose -p orar_test -f docker-compose.test.yml up -d --build orar_bot
docker compose -p orar_test -f docker-compose.test.yml logs --tail 80 orar_bot
```

Use the admin setup above with the same test project/file arguments, not the
production Compose command. Uploads write only to `.test-env/schedules/`;
`session_test` stays separate from `session_master`. Copy matching sidecars if
testing existing classified schedules. Rebuild after code or locale changes.

```sh
docker compose -p orar_test -f docker-compose.test.yml stop
```

`down -v` deletes this test project's named MySQL volume. Use it only when
intentionally resetting disposable test data, never during a production upgrade.
It does not delete production's `./mysql` bind directory, but `down` still stops
the whole stack. Private refresh paths are in ignored `RUN_PRIVATE.md`.

### Regression checks

These tests use synthetic inputs, not Telegram or a production database:

```sh
python -m pip install -r requirements.txt
python -m pip check
python -m unittest discover -s tests -t tests -p 'test_*.py'
git diff --check
```

Tests live in `tests/`. Restrict a run with `-p`, for example
`-p 'test_emoji_setting.py'`. They generate their own workbooks and import bot
modules from a temporary sandbox, so run them from the repository root.

CI also builds the regular image and runs `tests/image_smoke.py` without network access.

## 🔍 Troubleshooting

| Problem | Check |
| --- | --- |
| Bot exits with database connection error | Check MySQL health/logs, config credentials, and initialized schema. Restarting does not reset or migrate MySQL. |
| Missing/invalid `settings.emoji` | Prepare the column manually as `BOOLEAN NOT NULL DEFAULT 1` before deploying. Preserve existing choices; no startup migration runs. |
| Missing `app_settings` or `current_year` | Prepare required table/settings manually. Do not replay full initialization SQL against live data. |
| Missing `contributors.csv` or group catalog | Supply contributors file and at least one valid active schedule before startup. |
| Telegram config unavailable | Check `ORAR_CONFIG` and its read-only mount. Verify credentials locally, without printing them. |
| Permission denied | Inspect the failing mount and actual container UID/GID. Fix ownership narrowly; do not hardcode UID 1000 or apply recursive `chmod 755`. |
| Wrong schedule or raw class text | Check workbook path/layout, selected study year/group, and sidecar hash. Uncertain or missing classifications deliberately retain raw text. |
| Backup fails | Check executable, credentials, disk space, permissions, and dump privileges. Failed/empty/timed-out dumps are not sent; partial temporary files are removed when cleanup succeeds. |

For interrupted publication or failed rollback, obtain approval and stop only
the bot. Restore matching workbook/sidecar/catalog backups, preserve independently
published years and later legitimate updates, validate hashes, then restart.
Restoring RAM alone does not repair disk state.
