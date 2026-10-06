# 🤖 ORAR UTM FCIM BOT

Welcome! This document provides a comprehensive guide to setting up, running, and managing the ORAR UTM FCIM Telegram Bot using Docker.

## 📋 Table of Contents
- [Introduction](#-introduction)
- [Prerequisites](#️-prerequisites)
- [Setup and First Run](#-setup-and-first-run)
- [Configuration Details](#️-configuration-details)
- [Schedule File Format](#️-schedule-file-format)
- [Managing the Bot](#️-managing-the-bot)
- [Troubleshooting](#-troubleshooting)

## ✨ Introduction

This Telegram bot provides students of the UTM FCIM faculty with easy access to their academic schedules. It supports fetching schedules by day or week and sends notifications for upcoming classes.

The recommended setup uses Docker to ensure a consistent and reliable environment.
> **Note:** This setup has been tested only on Linux and macOS.

## 🛠️ Prerequisites

Before you begin, ensure you have the following installed:

-   [**Docker**](https://docs.docker.com/engine/install/)
-   [**Docker Compose**](https://docs.docker.com/compose/install/)
-   [**Git**](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

## 🚀 Setup and First Run

Follow these steps to get the bot running.

### 1. Clone the Repository

First, clone the project to your local machine and navigate into the directory.

```bash
git clone https://github.com/vaniok56/ORAR_UTM_FCIM_BOT.git
cd ORAR_UTM_FCIM_BOT
```

### 2. Create Configuration Files

You need to create two essential configuration files: `config.ini` and `mysql.env` in the `configs/` directory. Templates are provided, so you can copy them.

```bash
cp configs/config.ini.template configs/config.ini
cp configs/mysql.env.template configs/mysql.env
```

Next, **edit these new files** with your specific credentials as described in the [Configuration Details](#️-configuration-details) section below.

### 3. Prepare the Database

This step automatically configures the database initialization script.

```bash
# 1. Copy the database script template
cp init/init.sql.template init/init.sql

# 2. Automatically replace credentials in init.sql
# This command reads your credentials from configs/mysql.env and safely updates the SQL script.
export $(grep -v '^#' configs/mysql.env | xargs) && \
sed -i.bak "s/'your_user'/'$MYSQL_USER'/g; s/'your_password'/'$MYSQL_PASSWORD'/g" init/init.sql
```
> **Note:** The `sed` command creates a backup `init.sql.bak`. You can safely delete it after confirming `init.sql` was modified correctly.

### 4. Build and Run the Bot

Now, you can build the Docker image and launch the services. For the first start, it's recommended to run without detached mode to see potential issues.

```bash
sudo docker build --tag orar_bot . && sudo docker compose up
```

> **Note:** The first start will take a while. Don't panic if you see errors. You should wait for `[CRITICAL] Failed to establish MySQL connection`, after which MySQL reinitializes and the script will start.

Once it has started successfully, `/start` the bot in Telegram to initialize your user record in the database. After that, stop the bot (e.g., by pressing `Ctrl+C`) and start it normally in the background:

```bash
    sudo docker compose down && \
    sudo docker build --tag orar_bot . && \
    sudo docker compose up -d && \
    sudo docker logs -f -n 500 orar_bot
```

> **Note:** The `sudo docker logs -f -n 500 orar_bot` command allows you to follow the bot's logs in real-time, which is helpful for debugging and ensuring everything is running smoothly. You can Ctrl+C to stop following the logs without stopping the container.

### 5. Make Yourself an Admin

To manage the bot via Telegram, you need to grant yourself admin privileges in the database.

1. First, find your Telegram ID in the database (replace `{password}` with your `MYSQL_ROOT_PASSWORD`):
   ```bash
   sudo docker exec -it orar_mysql mysql -u root -p{password} orar_bot -e "SELECT * FROM users;"
   ```

2. Update your user record to make yourself an admin (replace `{YOUR_TELEGRAM_ID}` with your Telegram ID from the previous step, including the "U" prefix, e.g., `U123456789`):
   ```bash
   sudo docker exec -it orar_mysql mysql -u root -p{password} orar_bot -e \
   "UPDATE settings s \
   JOIN users u ON s.id = u.id \
   SET s.admins = 1 \
   WHERE u.SENDER = '{YOUR_TELEGRAM_ID}';"
   ```

3. Verify that you are now an admin:
   ```bash
   sudo docker exec -it orar_mysql mysql -u root -p{password} orar_bot -e \
   "SELECT u.SENDER, s.admins \
   FROM users u \
   JOIN settings s ON u.id = s.id \
   WHERE u.SENDER = '{YOUR_TELEGRAM_ID}';"
   ```

> **Important:** You need to restart the container for the changes to apply:
> ```bash
> sudo docker compose down && \
> sudo docker build --tag orar_bot . && \
> sudo docker compose up -d && \
> sudo docker logs -f -n 500 orar_bot
> ```

### 6. Fix Backup Permissions

To allow the bot to write database backups, you need to set the correct permissions for the `backups` directory:

```bash
sudo chown -R 1000:1000 ./backups && \
sudo chmod -R 755 ./backups
```

Your bot is now running! 🎉

## ⚙️ Configuration Details

### `configs/config.ini`

This file holds your Telegram API credentials.

```ini
[default]
api_id = YOUR_API_ID
api_hash = YOUR_API_HASH
BOT_TOKEN = YOUR_BOT_TOKEN
```

-   `api_id` and `api_hash`: Obtain these from [my.telegram.org](https://my.telegram.org).
-   `BOT_TOKEN`: Get this from [@BotFather](https://t.me/BotFather) on Telegram by creating a new bot.

### `configs/mysql.env`

This file configures the database credentials.

```env
MYSQL_DATABASE=orar_bot
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_ROOT_PASSWORD=root_password
```

> **Security:** Choose a strong, unique password for `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_ROOT_PASSWORD`. These files are ignored by Git to prevent accidentally exposing secrets.

## 🗓️ Schedule File Format

The bot reads schedules from Excel files placed in the `schedules/` directory.

-   **Naming Convention**: `orar<year>.xlsx`, where `<year>` is the academic year (1-4).
    -   Example: `orar1.xlsx`, `orar2.xlsx`, etc.
-   **File Structure**:
    -   The data must be in a sheet named **"Table 2"**.
    -   **Row 1, Column A**: Contains the version of the schedule.
    -   **Row 1**: Contains group names (e.g., "TI-241") starting from **Column C**.
    -   **Column A**: Contains the day of the week (e.g., "Luni", "Marţi").
    -   **Column B**: Contains the class time intervals (e.g., "8.00-9.30").
    -   The intersection of a group's column and a time slot's row contains the class details (subject, teacher, room).

An example file, `orar_example.xlsx`, is provided for reference.

## 🕹️ Managing the Bot

### Stopping the Bot

To stop the bot and shut down all services:

```bash
sudo docker compose down
```

### Updating the Bot

To update the bot with the latest changes from the Git repository:

```bash
# 1. Stop the running services
sudo docker compose down

# 2. Pull the latest code
git pull

# 3. Rebuild the image and restart the services
sudo docker build --tag orar_bot . && sudo docker compose up -d
```

### Resetting the Database

To completely wipe the database and start fresh:

```bash
# 1. Stop the services
sudo docker compose down

# 2. Remove the MySQL data volume
sudo rm -rf ./mysql

# 3. Restart the services. Docker will re-create the database using init.sql.
sudo docker compose up -d
```

## Local test bot on Mac

Mac and private stage share the test Telegram token. Stop one before starting
the other. Live Telegram/stage checks require a separate execution decision.

Run from the repository root. This setup uses `configs/config2.ini` for the test
Telegram bot, an independent `orar_test` Docker project, a fresh named MySQL
volume, and `.test-env/` for schedules, logs, backups, and the Telegram session.
Neither container publishes a host port. Do not run the normal
`docker-compose.yml` for this test: it publishes MySQL on port 3306 and mounts
the regular `mysql/` and `sessions/` directories.

First-time preparation (already done on this Mac):

```bash
mkdir -p .test-env/{schedules,sessions,logs,backups}
chmod 700 .test-env .test-env/{schedules,sessions,logs,backups}
cp -p schedules/orar{1,2,3,4}.xlsx .test-env/schedules/
cp -p contributors.csv .test-env/contributors.csv
chmod 600 configs/config2.ini configs/mysql.env .test-env/contributors.csv
```

`init/init.sql` must match the credentials in `configs/mysql.env`; the test
Compose file mounts only that initialization script, not migration scripts.
Initialize and check the isolated database:

```bash
docker compose -p orar_test -f docker-compose.test.yml up -d mysql
docker compose -p orar_test -f docker-compose.test.yml ps
```

For the Telegram account currently hardcoded as `main_admin` in
`src/handlers/admin_handlers.py`, seed admin rank **before** starting the bot.
This modifies the test database only. If you use a different Telegram account,
replace the ID below with its `U`-prefixed ID:

```bash
docker compose -p orar_test -f docker-compose.test.yml exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -D orar_bot' <<'SQL'
CALL add_new_user('U500303890');
UPDATE settings SET admins=1
WHERE id=(SELECT id FROM users WHERE SENDER='U500303890');
SQL
```

Build and start the test bot, then check logs and send `/start`, `/admin_help`,
and `/today` to the **test** bot in Telegram:

```bash
docker compose -p orar_test -f docker-compose.test.yml up -d --build orar_bot
docker compose -p orar_test -f docker-compose.test.yml logs --tail 80 orar_bot
```

`/update_schedule` writes only to `.test-env/schedules/`. The test bot session
is `.test-env/sessions/session_test.session`; the regular `session_master`
is untouched. The database persists across stops. Code or locale changes
require rebuilding the test bot with the `up -d --build orar_bot` command above.
`/update_schedule` collects **1–8 files**: dean-layout XLSX (20 MiB max)
and optional matching PDF (30 MiB max), at most one each per Year 1–4. Send
in any order or Telegram album, then tap **Review uploads**; omitted PDFs
mean XLSX-only audit. PDF without XLSX cannot publish. Bot pairs academic
year, study year, and semester from file titles; academic year itself is
unrestricted. PDF filename provides version when recognized; for XLSX-only
or versionless PDF, send `YEAR=1`–`YEAR=99` or `YEAR=final` when prompted,
then tap **Review uploads** again. Bot sends independent audit/diff reports
and Publish Year buttons; no year publishes until clicked. Each year can
publish independently. Same/older revisions and PDF text-audit findings need
explicit review; parser/layout/source-output failures cannot publish.
Staging lives under `.test-env/schedules/.uploads/` and expires after 30
minutes of idle time, refreshed only by accepted files/versions and valid
Review/Publish actions. Duplicate files require restarting the batch. Manual
versions win over PDF filename guesses, with a warning. Once review is prepared,
editing ends. Stale targets or publication failures clear remaining batch;
already-published years stay committed. Sunday/seven-day uploads reject.
Published output saves classifications beside it as
`orarN.classifications.json`; uncertain labels keep raw text. Review CSV records
source coordinates and XLSX hash; changed-cell CSV identifies displayed
**ISO-even/ISO-odd** weeks. Previous XLSX, sidecar, and group catalog copies
stay under `.test-env/schedules/rollback/` after publication. Check `/today`,
`/curr_week`, reminders, and restart persistence. Existing test schedules
need matching sidecars when testing without upload.

Private schedule-refresh host paths live in ignored `RUN_PRIVATE.md`. Compare
all SHA-256 hashes before replacing local copies; restart only the test bot.

Stop the local test without deleting its database:

```bash
docker compose -p orar_test -f docker-compose.test.yml stop
```

Do not use `down -v`: it deletes the test database volume. Check isolation with
`docker compose -p orar_test -f docker-compose.test.yml ps`; the `PORTS` column
must not show a published host address.

## Runtime configuration and checks

`/emoji` saves a per-user preference for schedule content, `/hours`, and both
reminder types. Existing users default OFF when the bot first adds the
`settings.emoji` column; future users default ON. Restarting does not reset
choices. OFF uses the original raw course text (HTML-escaped); menus and status
emojis are unchanged. The settings message contains a fixed illustrative sample
unrelated to any date or user schedule: three pairs covering
lecture, seminar, and a single subgroup-2 lab. With emojis ON, `c.` subjects use
🎙️; `sem.` and unprefixed subjects use 📖. Prefixes remain visible and lab markers
preserve the source's `lab` spelling and case.
Whole-group labs use one line (`🌕 lab. BD1`), without a book icon; half-group
labs keep their marker and book-prefixed subject on separate lines.
Its inline button shows the current state and switches the saved preference and preview in place.

Production uses read-only `/configs/config.ini`; Mac/stage set
`ORAR_CONFIG=configs/config2.ini`. Production base pins Python 3.14.8 bookworm.

```sh
python -m pip install -r requirements.txt
python -m pip check
python -m unittest test_schedule_ingest test_upload_status
docker build -t orar-pr4-smoke .
docker run --rm --network none \
  --mount type=bind,source="$PWD/tests",target=/checks/tests,readonly \
  --mount type=bind,source="$PWD/test_schedule_ingest.py",target=/checks/test_schedule_ingest.py,readonly \
  orar-pr4-smoke python /checks/tests/image_smoke.py
```

Checks use synthetic inputs only. Upload caps: 2,000 rows, 1,024 columns,
100,000 cells, 2,000 merges, 20,000 merged cells, 100 groups; measured maxima:
873, 518, 27,689, 793, 3,368, 42. Existing size/archive caps remain. PDF timeout:
30 seconds.

## Manual recovery after interrupted publication

Normal failures restore files and RAM. Rollback errors alert uploader/admin and
leave durable copies in `schedules/rollback/`. Before manual recovery, stop bot;
restore matching workbook/sidecar/catalog copies, preserve independently
published years, validate workbook/sidecar hashes, then restart. RAM state alone
does not make disk safe for restart.

## 🔍 Troubleshooting

If you encounter issues, check the following:

-   **Permission Denied Errors**:
    -   This is common on Linux/macOS if the `./mysql` or `./backups` directory permissions are incorrect.
    -   **Solution**: Stop the bot (`sudo docker compose down`), ensure the directories have the correct permissions (e.g., `sudo chown -R 1000:1000 ./mysql ./backups` and `sudo chmod -R 755 ./mysql ./backups`), and restart.

-   **Database Connection Issues**:
    -   Check the database logs for errors: `sudo docker logs orar_mysql`.
    -   **Solution**: Ensure the credentials in `configs/mysql.env` are correct and that you have run the `sed` command in [Step 3](#3-prepare-the-database) to update `init.sql` correctly.

-   **Bot Is Unresponsive**:
    -   Check the bot's logs: `sudo docker logs orar_bot`.
    -   **Solution**: This is often caused by incorrect Telegram credentials. Verify that `api_id`, `api_hash`, and `BOT_TOKEN` in `configs/config.ini` are correct.

-   **Incorrect Schedule Displayed**:
    -   **Solution**: Verify that your `orar<year>.xlsx` files are correctly named, located in the root directory, and follow the format specified in the [Schedule File Format](#️-schedule-file-format) section.
