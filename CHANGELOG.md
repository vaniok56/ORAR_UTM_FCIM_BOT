# Changelog

All notable changes to ORAR_UTM_FCIM_BOT will be documented in this file.

## [0.13.2] - 2026-03-02

### TL;DR
This release standardizes bot commands by renaming Romanian commands to their English equivalents. It also brings improvements to the Docker configuration to ensure more reliable startup and better build contexts.

### Updated
- **Bot Commands** ([`src/script.py`](./src/script.py), [`src/handlers/group_handlers.py`](./src/handlers/group_handlers.py), [`locales/`](./locales/), [`README.md`](./README.md)):
    - Renamed all Romanian commands to standardized English commands for global consistency:
        - `/azi` -> `/today`
        - `/maine` -> `/tomorrow`
        - `/ore` -> `/hours`
        - `/sapt_curenta` -> `/curr_week`
        - `/sapt_viitoare` -> `/next_week`
        - `/alege_grupa` -> `/choose_gr`
        - `/alege_subgrupa` -> `/choose_subgr`
        - `/donatii` -> `/donations`
    - Reordered the output for the `/help` command.
    - Updated `lang_callback` to send a new localized keyboard as a separate message instead of replacing the old one inline.
- **Docker Configuration** ([`docker-compose.yml`](./docker-compose.yml), [`.dockerignore`](./.dockerignore)):
    - Increased MySQL container healthcheck interval to `5s` and retries to `60` to prevent timeout failures on slower systems.
    - Added `condition: service_healthy` to `orar_bot` dependency on `mysql` to prevent premature startup.
    - Refactored `.dockerignore` to use wildcards `**` (e.g. `**.env`, `**.DS_Store`, etc.) and ensure `Dockerfile`, macOS/Windows system files, and backups are correctly ignored.
- **Documentation** ([`RUN.md`](./RUN.md), [`README.md`](./README.md)):
    - Updated `README.md` to reflect new standardized command aliases and fixed formatting issues.
    - Fixed formatting and markdown block indentation in `RUN.md`.

## [0.13.1] - 2026-02-22

### TL;DR
This release focuses on improving the Docker setup and documentation, fixing database backup automation, and cleaning up database logging.

### Updated
- **Docker Configuration** ([`docker-compose.yml`](./docker-compose.yml)):
    - Removed the hardcoded `user: "1000:1000"` from the MySQL service to prevent permission issues on different host systems.
    - Added `env_file: configs/mysql.env` to the MySQL service to properly load environment variables.
    - Renamed the bot service and image from `orarbot` to `orar_bot` for consistency.
    - Mounted the entire `./src` directory instead of just `./src/dynamic_group_lists.py`.
- **Documentation** ([`RUN.md`](./RUN.md)):
    - Completely overhauled the setup instructions.
- **File Tracking** ([`.gitignore`](./.gitignore)):
    - Updated the ignore rule for `dynamic_group_lists.py` to `/src/dynamic_group_lists.py`.

### Fixed
- **Database Backup Automation** ([`src/script.py`](./src/script.py)):
    - Added a check in `backup_database()` if admins exist before attempting to send backup files.
- **Database Logging** ([`src/handlers/db.py`](./src/handlers/db.py)):
    - Removed unnecessary "No users found" info logs from `get_all_users_with` and `get_all_users_without`.

## [0.13.0] - 2026-02-22

### TL;DR
This release introduces full localization support (Romanian, Russian, English), allowing users to choose their preferred language. It also includes database updates to store language preferences, enhancements to admin statistics to track language usage, and fixes for user data caching.

### Added
- **Localization System** ([`src/localization.py`](./src/localization.py), [`locales/`](./locales/)):
    - Implemented a new localization module to handle multi-language support.
    - Added translation files for English (`en.json`), Romanian (`ro.json`), and Russian (`ru.json`).
    - Added a new `/language` command for users to switch their preferred language.
    - The `/start` command now prompts new users to select their language before proceeding.
- **Database Updates** ([`init/init.sql.template`](./init/init.sql.template)):
    - Added a `lang` column to the `settings` table to store user language preferences.
    - Updated stored procedures (`migrate`, `get_all_users`, `select_all_user_data`, etc.) to include the new `lang` field.

### Updated
- **Bot Commands & Handlers** ([`src/script.py`](./src/script.py), [`src/handlers/group_handlers.py`](./src/handlers/group_handlers.py), [`src/functions.py`](./src/functions.py)):
    - Refactored all user-facing messages, keyboards, and notifications to use the new localization system.
    - Keyboard buttons (`bot_kb`, `start_kb`) are now generated dynamically per language (`build_bot_kb`, `build_start_kb`).
    - Updated schedule formatting functions (`print_day`, `print_daily`, `print_next_course`, `print_sapt`) to support localized weekday names and labels.
    - Background tasks (`prepare_next_courses`, `send_schedule_tomorrow`, `send_notification`) now fetch and use the user's preferred language for notifications.
    - The `/donatii` command now includes a "Buy me a coffee" inline button with a URL.
- **Admin Statistics** ([`src/handlers/admin_handlers.py`](./src/handlers/admin_handlers.py)):
    - The `/stats` command now tracks and displays the distribution of users across different languages (Romanian, Russian, English).
- **File Tracking** ([`.gitignore`](./.gitignore)):
    - Stopped tracking `src/dynamic_group_lists.py` in version control.

### Fixed
- **Database Caching** ([`src/handlers/db.py`](./src/handlers/db.py)):
    - Fixed an issue where the user data cache was not being properly refreshed after calling `update_user_field` by explicitly calling `locate_field` to refresh the cache.

## [0.12.3] - 2026-01-27

### TL;DR
This release improves logging robustness, optimizes broadcast messaging by uploading media only once, enhances schedule version parsing from the website, and cleans up error reporting for notifications.

### Updated
- **Logging & Paths** ([`src/functions.py`](./src/functions.py)):
    - Improved log directory resolution to correctly locate the project root relative to the source file.
    - Added fallbacks for log directory creation and file handling to prevent crashes on permission errors.
    - Updated `write_groups_to_json` to correctly resolve the path for `dynamic_group_lists.py` and skip writing if no groups are loaded.
- **Schedule Parsing** ([`src/functions.py`](./src/functions.py)):
    - Enhanced `get_online_schedule_versions` to more robustly locate the correct table row on the FCIM website (`Orar Semestrul de`).
    - Updated filename regex to handle more variations in schedule filenames (e.g., lowercase roman numerals, extra dates).
- **Admin Tools** ([`src/handlers/admin_handlers.py`](./src/handlers/admin_handlers.py)):
    - Optimized `/message` broadcast: media is now uploaded once and reused for all recipients, significantly speeding up large broadcasts.
    - Added progress logging and summary statistics (sent/errors) for broadcasts.
    - Added error handling to `/debug_next` to prevent crashes.
- **Notifications** ([`src/script.py`](./src/script.py)):
    - Reduced log noise in `prepare_next_courses` by aggregating error counts instead of logging each failure individually.

### Fixed
- **Admin Handlers** ([`src/handlers/admin_handlers.py`](./src/handlers/admin_handlers.py)):
    - Fixed an issue in `user_status_management` where cleaning up the waiting state could raise a KeyError.

## [0.12.2] - 2026-01-23

### TL;DR
This release enhances the schedule versioning system to support "final" versions, introduces a contributors role for managing schedules without full admin access, and updates the bot's startup sequence.

### Added
- **Contributors System** ([`handlers/admin_handlers.py`](./handlers/admin_handlers.py)):
    - New `/contrib` command to list authorized contributors.
    - New `/edit_contrib` command (Main Admin only) to add/remove contributors and assign them permissions for specific academic years.
    - Contributors can now use `/update_schedule` for their assigned years.
    - Mounted `contributors.csv` in `docker-compose.yml` to persist contributor data.

### Updated
- **Schedule Versioning** ([`functions.py`](./functions.py), [`script.py`](./script.py)):
    - Optimized `/version` command to correctly display and compare "final" schedule versions (filenames without numbers) alongside numbered versions (e.g., "v12").
    - Improved parsing logic in `get_online_schedule_versions` and `get_local_schedule_versions` to handle various data types (floats, strings) and filenames.
- **Bot Startup** ([`script.py`](./script.py)):
    - Refactored entry point to use `asyncio.run(main())` because python 3.11+ deprecates `get_event_loop()`.
- **Admin Rate Limiting** ([`handlers/admin_handlers.py`](./handlers/admin_handlers.py)):
    - Removed rate limit checks for admin commands to ensure smoother administration.

### Fixed
- **Docker**: Removed `*.csv` from `.dockerignore` and added volume mapping for `contributors.csv`.

## [0.12.1] - 2025-09-27

### TL;DR
Patch release with configurations path fixes, small robustness improvements to schedule parsing and database handling, and documentation updates.

### Added
- Added repository templates and configuration under `configs/` (`config.ini.template`, `mysql.env.template`, `my.cnf`) to centralize configuration files.

### Updated
- Packages versions in `requirements.txt`. Tested for stability.
- Docker & compose (`Dockerfile`, `docker-compose.yml`): simplified docker-cli base image, fixed mounted config paths to `configs/`, and improved healthcheck timing.
- Script & config paths (`script.py`, `RUN.md`): updated to read `configs/config.ini` and reference `configs/mysql.env` for consistent file locations.
- Database connection handling (`handlers/db.py`): improved connection-pool initialization, explicit port usage, unique pool naming, and more robust stored-procedure result processing when preloading users.

### Fixed
- Corrected stored-procedure result processing to avoid unread-result errors when preloading user cache (`handlers/db.py`).
- Minor parsing and type-conversion fixes to prevent crashes when Excel cells contain NaN or unexpected types (`functions.py`).

## [0.12.0] - 2025-09-11

### TL;DR
This release introduces a major feature: automatic schedule update checking. The bot now monitors the official FCIM website for new schedule versions and notifies admins if local files are outdated. The `/version` command has been enhanced to show a side-by-side comparison of local and online schedule versions. Additionally, the project structure has been cleaned up by moving schedule files into a dedicated `schedules` directory.

### Added
- **Schedule Update Checker** ([`functions.py`](./functions.py), [`script.py`](./script.py)):
    - The bot now fetches schedule version numbers from the FCIM website by running the command `/version`. 
    - It compares online versions with the versions of the local `orar*.xlsx` files.
- **Dynamic Schedule Loading & Updating** ([`functions.py`](./functions.py), [`handlers/admin_handlers.py`](./handlers/admin_handlers.py)):
    - Added a function to process and reload schedule files dynamically.
    - Introduced a new `/update_schedule` command for admins to upload new schedule files directly to the bot.
    - Caches are now cleared automatically when a new schedule file is processed.

### Updated
- **`/version` Command** ([`script.py`](./script.py)):
    - The command output now includes a detailed comparison of local versus online schedule versions for each academic year, making it easy to see what's current.
- **File Structure**:
    - All schedule Excel files (`orar*.xlsx`) have been moved from the root directory to the [`schedules/`](./schedules/) directory for better organization.
    - Code in [`functions.py`](./functions.py) has been updated to reflect the new file paths.
- **Documentation** ([`RUN.md`](./RUN.md)): Completely rewritten to provide a comprehensive, step-by-step guide for setup, configuration, and management.
- **Docker & Git** ([`.dockerignore`](./.dockerignore), [`.gitignore`](./.gitignore)): Updated to align with the new file structure and improve build context.

### Removed
- **Obsolete Files**:
    - Removed the old, unused `migrate.py` script.
    - Deleted `orar1.xlsx` and `orar2.xlsx` from the root directory, as they are now managed in the `schedules/` directory. Now only the example schedule is keeped in repository.

### Fixed
- **Admin Commands** ([`handlers/admin_handlers.py`](./handlers/admin_handlers.py)):
    - Refactored user management commands (`/ban`, `/unban`, `/admin`) for improved reliability and code structure.
    - Replaced hardcoded main admin ID with a dedicated constant.

## [0.11.2] - 2025-09-04

### TL;DR
This update enhances logging, refines the Docker environment, and improves the user experience for group selection. Key changes include moving to date-stamped log files in a dedicated `logs` directory, adding a MySQL configuration file for timezone and performance, and streamlining the initial bot interaction flow.

### Added
- [`my.cnf`](./my.cnf): New MySQL configuration file to set the timezone, optimize performance, and disable binary logging.
- [`sessions/.gitkeep`](./sessions/.gitkeep): Added to ensure the `sessions` directory is tracked by Git.

### Updated
- Logging ([`functions.py`](./functions.py)):
    - Logs are now stored in the [`logs/`](./logs/) directory with date-stamped filenames (e.g., `orarbot_04_09_25.log`).
    - The application ensures the `logs` directory exists at startup.
- Docker ([`docker-compose.yml`](./docker-compose.yml)):
    - Set the timezone for the MySQL container to `Europe/Chisinau`.
    - Mounted the new [`logs/`](./logs/) directory into the `orarbot` container instead of a single log file.
    - Added `PYTHONUNBUFFERED=1` to the bot's environment for better log output.
- Group Selection Flow ([`handlers/group_handlers.py`](./handlers/group_handlers.py), [`script.py`](./script.py)):
    - The `/start` command now presents a cleaner initial interface, prompting users to select their group immediately.
    - The group selection process (`/alege_grupa`) now feels smoother, clearing old buttons and showing the main keyboard upon completion.
- Code Refinements ([`functions.py`](./functions.py)):
    - Minor improvements to schedule and group constant definitions for better readability.

### Fixed
- Group Selection ([`handlers/group_handlers.py`](./handlers/group_handlers.py)): Fixed a bug where the wrong button variable was used when displaying the group selection menu.
- [`.gitignore`](./.gitignore): Adjusted to correctly handle session files and no longer ignore `.cnf` files.

## [0.11.1] - 2025-09-03

### TL;DR
This update focuses on improving Docker setup robustness, database connection stability, and adding comprehensive setup documentation. Key changes include adding a `RUN.md` guide, a SQL initialization template, and refining the Docker configuration for better reliability.

### Added
- [`RUN.md`](./RUN.md): A new comprehensive guide on how to set up and run the bot using Docker.
- [`init/init.sql.template`](./init/init.sql.template): A template for database initialization to simplify first-time setup.

### Updated
- [`docker-compose.yml`](./docker-compose.yml):
    - Set a fixed `user` for the MySQL service to avoid permission issues.
    - Set `restart: always` for the `restarter` service to ensure it always comes back online.
- [`handlers/db.py`](./handlers/db.py): Explicitly defined the MySQL port in connection settings and backup/restore commands for more reliable connections.
- [`.gitignore`](./.gitignore): Now ignores specific shell scripts (`*.sh`) and only the `init.sql` file instead of the whole directory.

### Fixed
- [`script.py`](./script.py): Removed an unnecessary `keep_network_alive` task.
- [`functions.py`](./functions.py): Added a `try-except` block to handle potential errors when converting `subgrupa` to an integer, preventing crashes.

## [0.11.0] - 2025-09-01

### TL;DR
Refactored schedule and group handling to be fully dynamic, generating group lists from Excel files at startup. Introduced dynamic versioning via the GitHub API. Added new admin commands for restoring backups (`/use_backup`) and advancing user academic years (`/new_year`).

### Added
- [`dynamic_group_lists.py`](./dynamic_group_lists.py) to store group information generated at runtime from schedule files.
- `/use_backup` admin command to restore the database from a selection of recent backups in [`handlers/admin_handlers.py`](./handlers/admin_handlers.py).
- `/new_year` admin command to increment the academic year for all users in [`handlers/admin_handlers.py`](./handlers/admin_handlers.py).
- `requests` library to [`requirements.txt`](./requirements.txt) for making GitHub API calls.
- `backups/` directory to [`.gitignore`](./.gitignore).

### Updated
- Refactored schedule data loading in [`functions.py`](./functions.py) to be dynamic, removing hardcoded file paths and adapting to available `orar*.xlsx` files.
- The bot now automatically generates group selection menus from schedule Excel files on startup ([`functions.py`](./functions.py), [`script.py`](./script.py)).
- The `/version` command now dynamically fetches the version and last update date from the latest GitHub commit ([`functions.py`](./functions.py), [`script.py`](./script.py)).
- Database backups are now stored in the `/backups/` directory with a full timestamp and are no longer deleted after being sent ([`script.py`](./script.py), [`handlers/admin_handlers.py`](./handlers/admin_handlers.py)).
- [`docker-compose.yml`](./docker-compose.yml) to mount the `backups` and `dynamic_group_lists.py` files.
- [`.dockerignore`](./.dockerignore) and [`.gitignore`](./.gitignore) for better file management and to include new backup/volume paths.
- [`README.md`](./README.md) and `/admin_help` command to include the new admin commands.
- `/start` message in [`script.py`](./script.py) to clarify that only 1st and 2nd-year schedules are currently available.

### Fixed
- Added error handling in [`handlers/group_handlers.py`](./handlers/group_handlers.py) for the year selection callback to prevent crashes if a selected year's schedule is not available.

## [0.10.4] - 2025-05-07

### TL;DR
Fixed several `CallbackQuery` handlers to use specific patterns, improving reliability and preventing unintended triggers. Added MySQL config file mounting in Docker and ignored it in git. Minor improvements to start and contact messages.

### Fixed
- Corrected `CallbackQuery` patterns in [`handlers/group_handlers.py`](./handlers/group_handlers.py) for year, specialty, group, and subgroup selection to use specific checks instead of generic handlers.
- Corrected `CallbackQuery` patterns in [`handlers/admin_handlers.py`](./handlers/admin_handlers.py) for the custom message feature (`/message`) confirmation steps.
- Corrected notification button data in `group_callback` in [`handlers/group_handlers.py`](./handlers/group_handlers.py) to use `b"noti_on"`/`b"noti_off"`.
- Corrected `CallbackQuery` pattern for notification preference handler (`notiff`) in [`script.py`](./script.py).

### Updated
- Added `*.cnf` to [`.gitignore`](./.gitignore) to ignore MySQL config files.
- Mounted `my.cnf` into the MySQL container in [`docker-compose.yml`](./docker-compose.yml).
- Improved `/start` message in [`script.py`](./script.py) to include the user's first name, disable link preview and warn users about not all schedules implemented.
- Removed unnecessary `link_preview=False` from `/contacts` message in [`script.py`](./script.py).

## [0.10.3] - 2025-04-30

### TL;DR
Fixed subgroup schedule display, database stored procedure handling, and background notification task logic. Improved database connection pooling and caching.

### Fixed
- Corrected schedule display for subgroup 1 when a course is split between subgroups in [`functions.py`](./functions.py).
- Resolved potential "unread result" errors by correctly handling stored procedure results in database functions in [`handlers/db.py`](./handlers/db.py).
- Fixed logic error in the background task for sending current course notifications (`send_curr_course_users`) in [`script.py`](./script.py).
- Improved reliability and logic of the background task for sending tomorrow's schedule notifications (`send_schedule_tomorrow`) in [`script.py`](./script.py).

### Updated
- Enhanced MySQL connection pool management (increased size, unique names, reinitialization on errors) for better stability and performance in [`handlers/db.py`](./handlers/db.py).
- Improved user data caching strategy, including preloading and fallback mechanisms during database issues in [`handlers/db.py`](./handlers/db.py).

## [0.10.2] - 2025-04-28

### TL;DR
Refactored group selection logic to use temporary storage, improving reliability. Fixed database functions for user count and existence checks. Corrected admin ID usage in background tasks and fixed notification logic. Updated version command and removed minor logging.

### Updated
- Refactored group selection flow in [`handlers/group_handlers.py`](./handlers/group_handlers.py) to use a temporary dictionary (`temp_selection`) for storing year and specialty choices before final database update.
- Ensured `backup_database` and `keep_network_alive` in [`script.py`](./script.py) use dynamically fetched admin IDs.
- Updated `/version` command in [`script.py`](./script.py) with the current version `0.10.2` and date `28-04-2025`.

### Fixed
- Corrected `get_user_count` in [`handlers/db.py`](./handlers/db.py) to properly retrieve and return the user count by processing all result sets.
- Corrected `is_user_exists` in [`handlers/db.py`](./handlers/db.py) to correctly check the cache first before querying the database.
- Corrected notification check in `send_notification` in [`script.py`](./script.py) to use `noti == 1` instead of `noti != 'on'`.
- Added missing log entry after successfully sending a notification in `send_notification` in [`script.py`](./script.py).

### Removed
- Removed some redundant debug logging calls from `update_user_field` and `locate_field` in [`handlers/db.py`](./handlers/db.py).

## [0.10.1] - 2025-04-27

### TL;DR
Improved new user onboarding with an inline group selection button. Optimized Docker builds and fixed `docker-compose` configurations. Adjusted rate limits, fixed notification logic, and resolved database admin retrieval issues. Added typing indicators for better UX.

### Removed
- Some commented-out code

### Added
- Callback handler for inline "Select Group" button on `/start` for new users.
- `.dockerignore` file to exclude unnecessary files from the Docker image.
- Added `SetTypingRequest` calls in several command handlers to show a "typing..." status

### Updated
- Optimized Dockerfile build process to leverage layer caching for requirements.
- Reduced `MAX_MESSAGES_PER_MINUTE` from 10 to 5.
- Modified `/start` command flow for new users to use an inline button instead of sending a command message.
- Added notifications and subgroup selection prompt that appears after a user changes their group
- Moved imports and variables for `is_rate_limited` to top
- `keep_network_alive` now calls Telethon to keep the its session active
- Admin lists are initialized just from db

### Fixed
- Fixed `get_admins` function in `handlers/db.py` to correctly parse results.
- Fixed scheduled tomorrow notification
- `docker-compose.yml` updated the container name targeted by the restarter, adjusted the restart times
- Changed volume paths in `docker-compose.yml` from absolute to relative.

## [0.10.0] - 2025-04-16

### Removed
- Games feature

### Added
- This changelog file (`CHANGELOG.md`)
- MySQL database integration for storing user and schedule data
- Migration script/process from `.csv` to MySQL
- User data caching mechanism
- VS Code workspace file (`*.code-workspace`)
- `.gitignore` file for better repository management

### Updated
- Updated Python version and package requirements in `requirements.txt`
- Refactored codebase to utilize MySQL for all data operations
- Enhanced logging output with colored level names