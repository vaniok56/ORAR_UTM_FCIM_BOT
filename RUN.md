## Docker

To run this bot using Docker, follow these steps:

### 1. Prerequisites

Make sure you have Docker and Docker Compose installed on your system.

CLI: https://docs.docker.com/engine/install/

Desktop: https://docs.docker.com/desktop/release-notes/

### 2. Configuration

You need to create two configuration files and a database init file: `config.ini`, `mysql.env` and `init.sql`. These files are ignored by Git for security reasons.

#### `config.ini`

Path: ORAR_UTM_FCIM_BOT/config.ini

This file contains your Telegram API credentials. Create a file named `config.ini` in the root of the project with the following content:

```ini
[default]
api_id = YOUR_API_ID
api_hash = YOUR_API_HASH
BOT_TOKEN = YOUR_BOT_TOKEN
```

Replace `YOUR_API_ID`, `YOUR_API_HASH`, and `YOUR_BOT_TOKEN` with your actual credentials from [my.telegram.org](https://my.telegram.org).

#### `mysql.env`

Path: ORAR_UTM_FCIM_BOT/mysql.env

This file contains the database credentials. Create a file named `mysql.env` in the root of the project with the following content:

```env
MYSQL_DATABASE=orar_bot
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_ROOT_PASSWORD=root_password
```

You can change the `your_user`, `your_password`, and `root_password` to your desired values.

#### `init.sql`

Path: ORAR_UTM_FCIM_BOT/init/init.sql

This file contains initializes the MySQL database the first time the database container starts.

Copy or rename the template the template:  
`cp init/init.sql.template init/init.sql`

Open init/init.sql and replace every placeholder user/password with the exact MYSQL_USER and MYSQL_PASSWORD values you set in mysql.env (do NOT use root credentials unless required).

### 3. Build and Run the Bot

Once you have created the configuration files, you can build and run the bot using the following command:

```bash
docker build --tag orarbot . && docker compose up
```

On some systems, you might need to use `sudo`:

```bash
sudo docker build --tag orarbot . && sudo docker compose up
```

The bot should now be running in a Docker container.
