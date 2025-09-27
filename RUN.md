# 🤖 ORAR UTM FCIM BOT

Welcome! This document provides a comprehensive guide to setting up, running, and managing the ORAR UTM FCIM Telegram Bot using Docker.

## 📋 Table of Contents
- [Introduction](#introduction)
- [Prerequisites](#prerequisites)
- [Setup and First Run](#-setup-and-first-run)
- [Configuration Details](#-configuration-details)
- [Schedule File Format](#-schedule-file-format)
- [Managing the Bot](#-managing-the-bot)
- [Troubleshooting](#-troubleshooting)

## ✨ Introduction

This Telegram bot provides students of the UTM FCIM faculty with easy access to their academic schedules. It supports fetching schedules by day or week and sends notifications for upcoming classes.

The recommended setup uses Docker to ensure a consistent and reliable environment.

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

Next, **edit these new files** with your specific credentials as described in the [Configuration Details](#-configuration-details) section below.

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

### 4. Handle Permissions (Linux/macOS)

The MySQL container runs as user `1000:1000` and needs permission to write to the `./mysql` data directory.

```bash
# Delete the mysql directory if it exists to ensure a clean start
sudo rm -rf ./mysql

# Create the directory for MySQL data
mkdir -p ./mysql

# Set the correct ownership and permissions
sudo chown -R 1000:1000 ./mysql
sudo chmod -R 755 ./init
```
> **Note for Docker Desktop users (Windows/macOS):** You can often skip this step, as Docker Desktop handles volume permissions automatically. If you encounter permission errors in the database logs, run these commands.

### 5. Build and Run the Bot

Now, you can build the Docker image and launch the services.

```bash
docker build --tag orarbot . && docker compose up
```

-   To run the bot in the background (detached mode), add the `-d` flag:
    ```bash
    docker build --tag orarbot . && docker compose up -d
    ```
-   If you are not using Docker in rootless mode, you may need `sudo`:
    ```bash
    sudo docker build --tag orarbot . && sudo docker compose up
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

The bot reads schedules from Excel files placed in the `schedules/`.

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
docker compose down
```

### Updating the Bot

To update the bot with the latest changes from the Git repository:

```bash
# 1. Stop the running services
docker compose down

# 2. Pull the latest code
git pull

# 3. Rebuild the image and restart the services
docker build --tag orarbot . && docker compose up -d
```

### Resetting the Database

To completely wipe the database and start fresh:

```bash
# 1. Stop the services
docker compose down

# 2. Remove the MySQL data volume
sudo rm -rf ./mysql

# 3. Restart the services. Docker will re-create the database using init.sql.
docker compose up -d
```

## 🔍 Troubleshooting

If you encounter issues, check the following:

-   **Permission Denied Errors**:
    -   This is common on Linux/macOS if the `./mysql` directory permissions are incorrect.
    -   **Solution**: Stop the bot (`docker compose down`), run the `chown` and `chmod` commands from [Step 4](#4-handle-permissions-linuxmacos), and restart.

-   **Database Connection Issues**:
    -   Check the database logs for errors: `docker logs orar_mysql`.
    -   **Solution**: Ensure the credentials in `configs/mysql.env` are correct and that you have run the `sed` command in [Step 3](#3-prepare-the-database) to update `init.sql` correctly.

-   **Bot Is Unresponsive**:
    -   Check the bot's logs: `docker logs orar_bot`.
    -   **Solution**: This is often caused by incorrect Telegram credentials. Verify that `api_id`, `api_hash`, and `BOT_TOKEN` in `configs/config.ini` are correct.

-   **Incorrect Schedule Displayed**:
    -   **Solution**: Verify that your `orar<year>.xlsx` files are correctly named, located in the root directory, and follow the format specified in the [Schedule File Format](#-schedule-file-format) section.
