# Changelog

All notable changes to ORAR_UTM_FCIM_BOT will be documented in this file.

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