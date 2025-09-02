# 📅 ORAR_UTM_FCIM_BOT

[![Telegram Bot](https://img.shields.io/badge/Orar_UTM-bot-blue?logo=telegram)](https://t.me/orar_utm_fcim_bot)
[![Contacts](https://img.shields.io/badge/Contacts-gray?logo=telegram)](https://t.me/vaniok56)

ORAR_UTM_FCIM_BOT is a Telegram bot made for UTM students to simplify access to their class schedules.

## 📋 Table of Contents
- [✨ Features](#✨-features)
  - [🎛️ Keyboard Buttons](#🎛️-keyboard-buttons)
  - [🔔 Notifications](#🔔-notifications)
- [📖 Usage Guide](#📖-usage-guide)
  - [Getting Started](#getting-started)
  - [Common Commands](#common-commands)
- [📜 Changelog](CHANGELOG.md)
- [💻 Run](RUN.md)
- [📄 License](#📄-license)

## ✨ Features

### 🎛️ Keyboard Buttons

Use these buttons to instantly access different parts of your schedule:

<img src="imgs/kb.jpg" alt="kb" width="450">

- **Orarul de azi 📅** - Get today's schedule, including times and cabinets.
- **Orarul de maine 📅** - See tomorrow's schedule.
- **Săptămâna curentă 🗓️** - View the schedule for the current week.
- **Săptămâna viitoare 🗓️** - View the schedule for next week.
- **SIMU📚** - Quick access to the student portal.

### 🔔 Notifications

Enable notifications at the start or use the `/notifon` command to receive:

- **Next class alert**: A notification 15 minutes before your next class(according to your subgroup, if you chose one), showing:
  - Class name
  - Professor name
  - Cabinet number
  - Class times

<img src="imgs/next_course.jpeg" alt="class" width="350">

- **Next day alert**: At 20:00, the bot sends the schedule for the following day.

<img src="imgs/next_day.jpeg" alt="schedule" width="400">

## 📖 Usage Guide

### Getting Started
1. Start the bot by sending `/start`
2. Select your group using `/alege_grupa`
3. Optionally select subgroup with `/alege_subgrupa`
4. Enable notifications with `/notifon`

### Common Commands

#### General Commands
- `/start` - Initialize the bot and choose notifications
- `/help` - Display available commands
- `/contacts` - Get developer contact info
- `/version` - Check bot version
- `/donatii` - Donation information

#### Schedule Commands
- `/azi` - Today's schedule
- `/maine` - Tomorrow's schedule
- `/ore` - Schedule of hours (class periods + breaks)
- `/sapt_curenta` - Schedule for the current week
- `/sapt_viitoare` - Schedule for next week

#### Settings Commands
- `/alege_grupa` - Select your group
- `/alege_subgrupa` - Select your subgroup
- `/notifon` - Turn on notifications
- `/notifoff` - Turn off notifications

#### Admin Commands
- `/admin_help` - Display admin commands
- `/stats` - View usage statistics
- `/backup` - Manual database backup
- `/use_backup` - Restore database from latest backup
- `/new_year` - Update all users' year (+1)
- `/message` - Send message to users
- `/ban` - Ban a user
- `/unban` - Unban a user
- `/list_ban` - List banned users

## 📄 License

This project is available as open source under the terms of the MIT License.