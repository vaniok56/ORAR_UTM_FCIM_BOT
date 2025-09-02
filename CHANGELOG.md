# Changelog

All notable changes to ORAR_UTM_FCIM_BOT will be documented in this file.

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