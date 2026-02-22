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
