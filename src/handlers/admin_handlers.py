import asyncio
import pandas as pd
import numpy as np
import datetime
import pytz
import os
import glob
from pathlib import Path

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

import handlers.db as db
from functions import activate_schedule, button_grid, send_logs, print_next_course, is_rate_limited, format_id, load_schedule_file, write_groups_to_json
from year_migration import plan_year_migration

moldova_tz = pytz.timezone('Europe/Chisinau')

current_year = 26  # (+1 each year)
main_admin = "U500303890"  # Your user ID here as string
contributors_df = pd.read_csv('contributors.csv')

def register_admin_handlers(client, admins1, admins2, specialties, group_list):
    draft = {}
    broadcast_task = None
    pending_auto_migrations = {}

    recipient_names = {
        1: "Myself",
        2: "TI-241",
        3: "Notifon users",
        4: "A user",
        5: "All users",
        6: "Year 1",
        7: "Year 2",
        8: "Year 3",
        9: "Year 4",
    }
    language_recipients = {1, 3, 5, 6, 7, 8, 9}

    def clear_draft():
        media_path = draft.get("media_path")
        if media_path:
            Path(media_path).unlink(missing_ok=True)
        draft.clear()

    def finish_broadcast(task):
        nonlocal broadcast_task
        broadcast_task = None
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as error:
            send_logs(f"Broadcast failed: {error}", "error")

    @client.on(events.NewMessage(pattern=r'^/cancel_message$'))
    async def cancel_message(event):
        if format_id(event.sender_id) != main_admin:
            return
        if not draft:
            await client.send_message(event.sender_id, "No active message draft.")
            return

        clear_draft()
        await client.send_message(event.sender_id, "Message draft canceled.")

    #/admin_help admin
    @client.on(events.NewMessage(pattern=r'^/admin_help$'))
    async def admin_help(event):
        sender = await event.get_sender()
        SENDER = sender.id
        uid = format_id(SENDER)
        send_logs(f"/admin_help called by {uid}, admins1={admins1}, admins2={admins2}", 'info')
        if uid not in admins1 and uid not in admins2:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        text = "Admin commands:\n\n"
        text += "/stats - show statistics\n\n"
        text += "/backup - manual database backup\n\n"
        text += "/use_backup - restore database from backup\n\n"
        text += "/message - send a message to users\n"
        text += "/cancel_message - cancel the current message draft\n\n"
        text += "/debug_next - debug print next course\n\n"
        text += "/auto_migrate - match user years to schedule groups\n\n"
        text += "Change user status:\n"
        text += "/ban - ban a user\n"
        text += "/unban - unban a user\n"
        text += "/list_ban - show banned users\n\n"
        text += "/admin - add a user as admin\n"
        text += "/unadmin - remove admin privileges\n"
        text += "/list_admin - show admin users\n\n"
        text += "/contrib - show contributors\n\n"
        text += "/edit_contrib - edit contributors\n\n"
        text += "/update_schedule - update schedule from file\n\n"
        text += "/auto_migrate - match user years to schedule groups\n\n"
        text += "/holidays - toggle holiday mode (pauses scheduled notifications)\n\n"
        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /admin_help", 'info')
        return
    
    #/stats admin
    @client.on(events.NewMessage(pattern=r'^/stats$'))
    async def statsss(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) not in admins1 and format_id(SENDER) not in admins2:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /stats - no acces", "info")
            return
        
        users_with_groups = db.get_all_users_without('group_n', 'none')
        
        group_counts = users_with_groups['group_n'].value_counts().to_dict()
        
        groups_by_year = {}
        categorized_groups = set()
        
        for group_name, count in group_counts.items():
            try:
                #TI-241 -> 24)
                year = int(group_name[-3:-1])
                
                if year not in groups_by_year:
                    groups_by_year[year] = {}
                
                groups_by_year[year][group_name] = count
                categorized_groups.add(group_name)
            except (ValueError, IndexError):
                pass
        
        text = "📊 Stats:\n\n"
        for year in sorted(groups_by_year.keys(), reverse=True):
            text += (f"🎓 Year {current_year-year}")
            sorted_groups = sorted(groups_by_year[year].items(), key=lambda x: (-x[1], x[0]))
            text += f" - {len(sorted_groups)} groups, {sum(count for group, count in sorted_groups)} users\n"

            for group, count in sorted_groups:
                text += f"  • {group}: {count} users\n"
            text += "\n"
        
        other_groups = {g: c for g, c in group_counts.items() if g not in categorized_groups}
        
        if other_groups:
            text += "📋 Other groups:\n"
            for group, count in sorted(other_groups.items(), key=lambda x: (-x[1], x[0])):
                text += f"  • {group}: {count} users\n"
            text += "\n"
        
        total_users = db.get_user_count()
        users_with_groups_count = len(users_with_groups)
        users_with_notifications = len(db.get_all_users_with('noti', 'on'))
        users_with_subgroups = len(db.get_all_users_without('subgrupa', 0))

        lang_ro = len(db.get_all_users_with('lang', 'ro'))
        lang_ru = len(db.get_all_users_with('lang', 'ru'))
        lang_en = len(db.get_all_users_with('lang', 'en'))
        
        text += f"📈 Summary:\n"
        text += f"  • Total users: {total_users}\n"
        text += f"  • Total users with groups: {users_with_groups_count}\n"
        text += f"  • Users with notifications: {users_with_notifications}\n"
        text += f"  • Users with selected sub-group: {users_with_subgroups}\n"
        text += f"🌐 Languages distribution:\n"
        text += f"  • Romanian: {lang_ro}\n"
        text += f"  • Russian: {lang_ru}\n"
        text += f"  • English: {lang_en}\n"

        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /stats", "info")

    #/message admin
    @client.on(events.NewMessage(pattern=r'^/message$'))
    async def message_command(event):
        if format_id(event.sender_id) != main_admin:
            await client.send_message(event.sender_id, "Nu ai acces!", parse_mode="HTML")
            return
        if draft:
            await event.reply("Finish or cancel current message draft.")
            return
        if broadcast_task and not broadcast_task.done():
            await event.reply("One broadcast is already scheduled or running.")
            return

        draft["step"] = "recipient"
        buttons = [
            Button.inline("Myself", data=b"to1"),
            Button.inline("TI-241", data=b"to2"),
            Button.inline("Notifon users", data=b"to3"),
            Button.inline("A user", data=b"to4"),
            Button.inline("Year 1", data=b"to6"),
            Button.inline("Year 2", data=b"to7"),
            Button.inline("Year 3", data=b"to8"),
            Button.inline("Year 4", data=b"to9"),
            Button.inline("All users", data=b"to5")
        ]
        message = await event.reply("Select the recipient:", buttons=button_grid(buttons, 2))
        draft["button_message_id"] = message.id

    @client.on(events.CallbackQuery(pattern=rb"^to[1-9]$"))
    async def message_callback(event):
        if format_id(event.sender_id) != main_admin:
            return
        if draft.get("step") != "recipient" or draft.get("button_message_id") != event.message_id:
            await event.answer("This message draft expired.", alert=True)
            return

        recipient = int(event.data[2:])
        draft.update(recipient=recipient, user_id=0, language=None)
        await event.answer()
        await event.edit("Selected: " + recipient_names[recipient])

        if recipient in language_recipients:
            draft["step"] = "language"
            lang_buttons = [
                Button.inline("RO 🇷🇴", data=b"message_lang_ro"),
                Button.inline("RU 🇷🇺", data=b"message_lang_ru"),
                Button.inline("EN 🇬🇧", data=b"message_lang_en"),
                Button.inline("Not set ❓", data=b"message_lang_notset"),
                Button.inline("All 🌐", data=b"message_lang_all")
            ]
            message = await client.send_message(event.sender_id, "Select the language of the recipients:", buttons=button_grid(lang_buttons, 3))
            draft["button_message_id"] = message.id
        elif recipient == 4:
            draft["step"] = "user"
            draft.pop("button_message_id", None)
            await client.send_message(event.sender_id, "Please enter the user ID(as int):")
        else:
            draft["step"] = "time"
            draft.pop("button_message_id", None)
            await client.send_message(event.sender_id, 'Please enter the time in HH:MM format or "Now":')

    @client.on(events.CallbackQuery(pattern=rb"^message_lang_(ro|ru|en|notset|all)$"))
    async def message_language(event):
        if format_id(event.sender_id) != main_admin:
            return
        if draft.get("step") != "language" or draft.get("button_message_id") != event.message_id:
            await event.answer("This message draft expired.", alert=True)
            return

        draft["language"] = event.data.decode().rsplit("_", 1)[1]
        draft["step"] = "time"
        draft.pop("button_message_id", None)
        await event.answer()
        await event.edit(f"Language selected: {draft['language']}")
        await client.send_message(event.sender_id, 'Please enter the time in HH:MM format or "Now":')

    @client.on(events.NewMessage(from_users=int(main_admin[1:])))
    async def message_input(event):
        user_input = event.text or ""
        if not draft or user_input.startswith("/"):
            return

        step = draft.get("step")
        if step == "user":
            try:
                draft["user_id"] = int(user_input)
            except ValueError:
                await event.reply("User ID must be an integer.")
                return
            draft["step"] = "time"
            await event.reply('Please enter the time in HH:MM format or "Now":')
            return

        if step == "time":
            if user_input.lower() != "now":
                try:
                    datetime.datetime.strptime(user_input, "%H:%M")
                except ValueError:
                    await event.reply('Invalid time. Use HH:MM or "Now".')
                    return
            draft["time"] = user_input
            draft["step"] = "content"
            await event.reply("Send your message (text or attach image/file with caption):")
            return

        if step != "content":
            return
        if not user_input and not event.media:
            return

        try:
            draft["media_path"] = await event.download_media("temp/") if event.media else None
        except Exception as error:
            send_logs(f"Error downloading media: {error}", "error")
            await event.reply(f"Error with media: {error}")
            return

        draft["text"] = user_input
        draft["step"] = "confirm"
        summary = f"\nSend to: {recipient_names[draft['recipient']]}"
        if draft["user_id"]:
            summary += f"\nUser ID: {draft['user_id']}"
        if draft["recipient"] in language_recipients:
            summary += f"\nLanguage filter: {draft['language']}"
        summary += f"\nTime: {draft['time']}\nMessage: \n{draft['text']}"
        await event.reply(summary)
        message = await event.reply(
            "Send the message?",
            buttons=[[Button.inline("Yes", data=b"send_mess_yes"), Button.inline("No", data=b"send_mess_no")]],
        )
        draft["button_message_id"] = message.id

    @client.on(events.CallbackQuery(pattern=rb"^send_mess_(yes|no)$"))
    async def message_confirmation(event):
        nonlocal broadcast_task
        if format_id(event.sender_id) != main_admin:
            return
        if draft.get("step") != "confirm" or draft.get("button_message_id") != event.message_id:
            await event.answer("This message draft expired.", alert=True)
            return

        if event.data == b"send_mess_no":
            clear_draft()
            await event.answer()
            await event.edit("Message sending canceled.")
            return

        campaign = draft.copy()
        draft.clear()
        broadcast_task = asyncio.create_task(send_mess(campaign))
        broadcast_task.add_done_callback(finish_broadcast)
        await event.answer("Scheduling message...")
        await event.edit("Message scheduled successfully!")

    #send the custom message
    async def send_mess(campaign):
        to_who = campaign["recipient"]
        when = campaign["time"]
        useridd = campaign["user_id"]
        text = campaign["text"]
        media_path = campaign.get("media_path")
        lang_filter = campaign.get("language")
        def cleanup_media():
            if media_path and os.path.exists(media_path):
                os.remove(media_path)
                send_logs(f"Removed temp file: {media_path}", 'info')

        try:
            if when.lower() != "now":
                scheduled = datetime.datetime.strptime(when, "%H:%M").time()
                now = datetime.datetime.now(moldova_tz)
                target_time = now.replace(
                    hour=scheduled.hour,
                    minute=scheduled.minute,
                    second=0,
                    microsecond=0,
                )
                if target_time <= now:
                    target_time += datetime.timedelta(days=1)
                try:
                    await asyncio.sleep((target_time - now).total_seconds())
                except asyncio.CancelledError:
                    cleanup_media()
                    raise

            if to_who == 1:
                all_users = db.get_all_users_with('SENDER', main_admin)
            elif to_who == 2:
                all_users = db.get_all_users_with('group_n', 'TI-241')
                send_logs("Sending to TI-241", 'info')
            elif to_who == 3:
                all_users = db.get_all_users_with('noti', '1')
                send_logs("Sending to notifon users", 'info')
            elif to_who == 4:
                all_users = db.get_all_users_with('SENDER', 'U'+str(useridd))
                send_logs("Sending to " + 'U'+str(useridd), 'info')
            elif to_who == 5:
                all_users = db.get_all_users()
                send_logs("Sending to everyone", 'info')
            elif to_who in [6, 7, 8, 9]:
                all_users = db.get_all_users_with('year_s', str(to_who - 5))
                send_logs(f"Sending to Year {to_who - 5}", 'info')
            else:
                send_logs("No users to send a message", 'info')
                cleanup_media()
                return
                
            if len(all_users) == 0:
                send_logs("No users found to send message to", 'warning')
                cleanup_media()
                return
        except Exception as e:
            send_logs(f"Error retrieving users for message: {e}", 'error')
            cleanup_media()
            return
        
        # Apply language filter for group broadcasts
        if lang_filter and lang_filter != 'all' and to_who in [1, 3, 5, 6, 7, 8, 9]:
            if 'lang' in all_users.columns:
                if lang_filter == 'notset':
                    all_users = all_users[all_users['lang'].isna() | (all_users['lang'] == '') | (all_users['lang'] == 'none')]
                else:
                    all_users = all_users[all_users['lang'] == lang_filter]
                send_logs(f"Filtered by language '{lang_filter}': {len(all_users)} users", 'info')
        
        try:
            uploaded_media = None
            if media_path and os.path.exists(media_path):
                try:
                    uploaded_media = await client.upload_file(media_path)
                except Exception as e:
                    send_logs(f"Error uploading media initially: {e}", 'error')

            sent_count = 0
            error_count = 0
            total_users = len(all_users)
            send_logs(f"Starting broadcast to {total_users} users...", 'info')

            for i, (_, row) in enumerate(all_users.iterrows()):
                user = row['SENDER']
                try:
                    sender = int(user[1:])
                    if uploaded_media:
                        await client.send_file(
                            sender,
                            uploaded_media,
                            caption=text,
                            parse_mode="Markdown"
                        )
                    elif media_path and os.path.exists(media_path):
                        await client.send_file(
                            sender,
                            media_path,
                            caption=text,
                            parse_mode="Markdown"
                        )
                    else:
                        await client.send_message(sender, text, parse_mode="Markdown")

                    sent_count += 1
                except Exception:
                    error_count += 1

                await asyncio.sleep(1 / 15)
                chunk = max(1, total_users // 10)
                if (i + 1) % chunk == 0:
                    send_logs(f"Broadcast progress: {i + 1}/{total_users}", 'info')

            send_logs(f"Broadcast finished. Sent to {sent_count}/{total_users} users (Errors: {error_count}).", 'info')
        finally:
            cleanup_media()

    #/debug_next admin
    @client.on(events.NewMessage(pattern=r'^/debug_next$'))
    async def debugg(event):
        sender = await event.get_sender()
        SENDER = sender.id
        subgrupa = db.locate_field("U"+str(event.sender_id), 'subgrupa')
        if "U"+str(event.sender_id) not in admins1:
            await client.send_message(event.sender_id, "Nu ai acces!", parse_mode="HTML")
            return
        
        week_day = int((datetime.datetime.now(moldova_tz)).weekday())
        is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
        try:
            for i in range(1, 8):
                text = "Perechea urmatore: #" + str(i)
                text += print_next_course(week_day, 'TI-241', is_even, i, subgrupa)
                if text:
                    await client.send_message(SENDER, text, parse_mode="HTML")
                send_logs(format_id(SENDER) + " - /debug_next", 'info')
        except Exception as e:
            send_logs(f"Error in /debug_next: {e}", 'error')
    
    #/backup admin
    @client.on(events.NewMessage(pattern=r'^/backup$'))
    async def manual_backup(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) != main_admin:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        try:
            #file
            now = datetime.datetime.now(moldova_tz)
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            os.makedirs("/backups", exist_ok=True)
            backup_filename = f"../backups/BD_backup_{timestamp}.sql"
            db.create_mysql_backup(backup_filename)
            db_len = db.get_user_count()
            #send
            await client.send_file(
                SENDER,
                backup_filename,
                caption=f"📊 Database backup\n{now.strftime('%Y-%m-%d %H:%M:%S')} - {db_len} users"
            )

            #delete
            # import os
            # if os.path.exists(backup_filename):
            #     os.remove(backup_filename)
                
            send_logs(f"Manual backup sent to {SENDER}", 'info')
        except Exception as e:
            send_logs(f"Error sending manual backup: {str(e)}", 'error')
            await client.send_message(SENDER, f"Error sending backup: {str(e)}", parse_mode="HTML")
    
    #/logs admin
    @client.on(events.NewMessage(pattern=r'^/logs$'))
    async def logs(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        try:
            #file
            now = datetime.datetime.now(moldova_tz)
            logs_filename = "orarbot.log"
            backup_filename = f"orarbot_{now.strftime('%Y%m%d')}.log"
            with open(logs_filename, 'r') as original_file:
                with open(backup_filename, 'w') as backup_file:
                    backup_file.write(original_file.read())
            #send
            await client.send_file(
                SENDER,
                backup_filename,
                caption=f"Logs\n{now.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            #delete
            import os
            if os.path.exists(backup_filename):
                os.remove(backup_filename)
                
            send_logs(f"Manual backup sent to {SENDER}", 'info')
        except Exception as e:
            send_logs(f"Error sending manual backup: {str(e)}", 'error')
            await client.send_message(SENDER, f"Error sending backup: {str(e)}", parse_mode="HTML")

    # Dictionary to track users waiting for actions
    user_action_waiting = {}
    
    # Helper function for user status management (ban/unban/admin)
    async def user_status_management(client, event, action_type):
        sender = await event.get_sender()
        SENDER = sender.id
        user_str = "U" + str(SENDER)

        if user_str not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return

        # Handle listing
        if action_type.startswith('list_'):
            system = action_type.split('_')[1]  # 'ban' or 'admin'
            if system == 'ban':
                text = "Banned users:\n"
                users = db.get_all_users_with('ban', 1)
                field_to_show_name = 'Time'
                field_to_show = 'ban_time'
                empty_message = "No banned users"
            elif system == 'admin':
                text = "Admin users:\n"
                users = pd.concat([
                    db.get_all_users_with('admins', 1),
                    db.get_all_users_with('admins', 2)
                ], ignore_index=True)
                field_to_show_name = 'Level'
                field_to_show = 'admins'
                empty_message = "No admin users"
            
            # Format and display the list
            if not users.empty:
                for _, row in users.iterrows():
                    user_id = row['SENDER']
                    field_value = row[field_to_show]
                    text += f"{user_id} - {field_to_show_name}: {field_value}\n"
            else:
                text += empty_message
            
            await client.send_message(SENDER, text, parse_mode="HTML")
            send_logs(f"{format_id(SENDER)} - /{action_type}", 'info')
            return
            
        # For actions that require user input (ban, unban, admin, unadmin)
        text = "Please enter the user ID(as int):"
        await client.send_message(SENDER, text)
        
        # Mark this user as waiting for input with the specific action
        user_action_waiting[SENDER] = action_type
        send_logs(f"{format_id(SENDER)} - initiated /{action_type} command", 'info')
        return
    
    # Handler for user input after ban/unban/admin commands
    @client.on(events.NewMessage())
    async def user_action_input_handler(event):
        # Skip command messages
        if event.text and event.text.startswith('/'):
            return
        
        sender = await event.get_sender()
        SENDER = sender.id
        
        # Check if this user is waiting
        if SENDER not in user_action_waiting:
            return
        
        action_type = user_action_waiting[SENDER]
        useridd = event.text
        try:
            useridd = int(useridd)
            user_str = "U" + str(useridd)
            
            # Handle different action types
            if action_type == 'ban':
                ban_time = datetime.datetime.now(moldova_tz) + datetime.timedelta(days=1)
                ban_time = ban_time.strftime("%d-%m-%y %H:%M:%S")
                db.update_user_field(user_str, "ban", 1)
                db.update_user_field(user_str, "ban_time", str(ban_time))
                await client.send_message(SENDER, f"User {user_str} banned", parse_mode="HTML")
            
            elif action_type == 'unban':
                db.update_user_field(user_str, "ban", 0)
                db.update_user_field(user_str, "ban_time", '')
                await client.send_message(SENDER, f"User {user_str} unbanned", parse_mode="HTML")
            
            elif action_type == 'admin':
                if user_str in admins1 or user_str in admins2:
                    await client.send_message(SENDER, f"User {user_str} is already an admin.", parse_mode="HTML")
                else:
                    admins2.append(user_str)
                    db.update_user_field(user_str, "admins", 2)
                    await client.send_message(SENDER, f"User {user_str} added as admin.", parse_mode="HTML")

            elif action_type == 'unadmin':
                if user_str in admins2:
                    admins2.remove(user_str)
                    db.update_user_field(user_str, "admins", 0)
                    await client.send_message(SENDER, f"User {user_str} removed from admins.", parse_mode="HTML")
                else:
                    await client.send_message(SENDER, f"User {user_str} is not an admin.", parse_mode="HTML")
            
            send_logs(f"{format_id(SENDER)} - /{action_type} - {user_str}", 'info')
        
        except ValueError:
            await client.send_message(SENDER, "Invalid user ID!", parse_mode="HTML")
        except Exception as e:
            send_logs(f"Error in {action_type} for user {useridd}: {str(e)}", 'error')
        finally:
            # Remove user from waiting list
            if SENDER in user_action_waiting:
                del user_action_waiting[SENDER]
    
    #/use_backup admin
    backup_to_restore = None

    @client.on(events.NewMessage(pattern=r'^/use_backup$'))
    async def use_backup(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) != main_admin:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        nonlocal backup_to_restore
        try:
            #find all backups
            backup_files = glob.glob("../backups/BD_backup_*.sql")
            if not backup_files:
                await client.send_message(SENDER, "No backup files found!", parse_mode="HTML")
                return
            backup_files.sort(key=os.path.getmtime, reverse=True)
            backup_to_restore = backup_files
            
            #format
            backup_list = "Available backups:\n\n"
            buttons = []
            #most recent 5 backups
            for i, backup_path in enumerate(backup_files[:5]):
                file_name = os.path.basename(backup_path)
                mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(backup_path), moldova_tz)
                #user count
                try:
                    user_count = "Unknown"
                    with open(backup_path, 'r') as f:
                        content = f.read()
                        if "INSERT INTO" in content:
                            user_count = content.count("'U")
                except Exception as e:
                    send_logs(f"Error reading backup file {file_name}: {str(e)}", 'error')
                    pass
                
                backup_list += f"{i+1}. {file_name}\n"
                backup_list += f"   📅 {mod_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                backup_list += f"   👥 Users: {user_count}\n\n"
                buttons.append(Button.inline(f"{i+1}. {file_name}", data=f"backup_{i}".encode()))
            buttons.append(Button.inline("Cancel", data=b"cancel_restore"))

            await client.send_message( SENDER, backup_list + "Select a backup to restore:", buttons=button_grid(buttons, 1), parse_mode="HTML")
            send_logs(f"User {SENDER} requested database restore options", 'info')
            
        except Exception as e:
            send_logs(f"Error listing backups for restore: {str(e)}", 'error')
            await client.send_message(SENDER, f"Error: {str(e)}", parse_mode="HTML")
    
    @client.on(events.NewMessage(pattern=r'^/cancel_restore$'))
    async def cancel_restore(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) != main_admin:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        global backup_to_restore
        backup_to_restore = None
        await client.edit_message(SENDER, event.message_id, "Database restoration cancelled.")
        send_logs(f"User {SENDER} cancelled database restore", 'info')

    @client.on(events.CallbackQuery(pattern=lambda x: x.startswith(b"backup_")))
    async def backup_selection_callback(event):
        nonlocal backup_to_restore
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) != main_admin:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        if not isinstance(backup_to_restore, list):
            await event.answer("No backups available")
            return
            
        try:
            # Get selected backup index
            backup_index = int(event.data.decode('utf-8').split('_')[1])
            selected_backup = backup_to_restore[backup_index]
            backup_to_restore = selected_backup
            
            # Ask for confirmation with the selected backup
            await event.answer(f"Selected: {os.path.basename(selected_backup)}")
            await client.edit_message(SENDER,event.message_id,
                f"⚠️ WARNING: This will replace your current database with backup:\n{os.path.basename(selected_backup)}\n\nDo you want to continue?",
                buttons=[
                    [Button.inline("Yes, restore database", data=b"confirm_restore")],
                    [Button.inline("Cancel", data=b"cancel_restore")]
                ])
            send_logs(f"User {SENDER} selected backup {selected_backup}", 'warning')
            
        except Exception as e:
            send_logs(f"Error processing backup selection: {str(e)}", 'error')
            await event.answer("Error selecting backup")
            await client.edit_message(SENDER, event.message_id, f"Error selecting backup: {str(e)}")

    @client.on(events.CallbackQuery(pattern=lambda x: x in [b"confirm_restore", b"cancel_restore"]))
    async def restore_callback(event):
        nonlocal backup_to_restore
        sender = await event.get_sender()
        SENDER = sender.id
        
        if event.data == b"cancel_restore":
            await event.answer("Restoration cancelled")
            await client.edit_message(SENDER, event.message_id, "Database restoration cancelled.")
            send_logs(f"User {SENDER} cancelled database restore", 'info')
            return
        
        if event.data == b"confirm_restore" and backup_to_restore:
            await event.answer("Starting restoration...")
            await client.edit_message(SENDER, event.message_id, "Database restoration in progress...")
            
            current_user_count = db.get_user_count()
            result = db.restore_backup(backup_to_restore)
            if result:
                #reinitialize
                db.initialize_mysql_connection()
                new_user_count = db.get_user_count()
                send_logs(f"Database restore successful from {backup_to_restore}", 'info')
                await client.edit_message(SENDER, event.message_id, 
                    f"✅ Database restored successfully from {os.path.basename(backup_to_restore)}\n\n" +
                    f"Users before: {current_user_count}\n" +
                    f"Users after: {new_user_count}")
            else:
                send_logs(f"Database restore failed from {backup_to_restore}", 'error')
                await client.edit_message(SENDER, event.message_id, f"❌ Database restore failed")

    @client.on(events.NewMessage(pattern=r'^/auto_migrate$'))
    async def auto_migrate(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) != main_admin:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return

        plan = plan_year_migration(db.get_all_users(), group_list)
        unknown_text = "\n".join(
            f"  {group}: {count}"
            for group, count in plan["unknown"].most_common(20)
        ) or "  none"
        if len(plan["unknown"]) > 20:
            unknown_text += f"\n  ...and {len(plan['unknown']) - 20} more; see logs"
        ambiguous_text = "\n".join(
            f"  {group}: {count}"
            for group, count in plan["ambiguous"].most_common(20)
        ) or "  none"
        if len(plan["ambiguous"]) > 20:
            ambiguous_text += f"\n  ...and {len(plan['ambiguous']) - 20} more; see logs"
        text = (
            "Academic year migration preview\n\n"
            f"Will update: {len(plan['updates'])}\n"
            f"Already correct: {plan['correct']}\n"
            f"No group: {plan['no_group']}\n"
            f"Unknown groups: {sum(plan['unknown'].values())}\n"
            f"Ambiguous groups: {sum(plan['ambiguous'].values())}\n\n"
            f"Unknown:\n{unknown_text}\n\n"
            f"Ambiguous:\n{ambiguous_text}"
        )
        message = await client.send_message(
            SENDER,
            text,
            buttons=[
                [Button.inline("Apply migration", data=b"apply_auto_migrate")],
                [Button.inline("Cancel", data=b"cancel_auto_migrate")],
            ],
        )
        pending_auto_migrations.clear()
        pending_auto_migrations[message.id] = plan["updates"]
        send_logs(
            f"Auto migration preview: {len(plan['updates'])} updates, "
            f"{sum(plan['unknown'].values())} unknown, "
            f"{sum(plan['ambiguous'].values())} ambiguous",
            "info",
        )
        if plan["unknown"]:
            send_logs(f"Auto migration unknown groups: {dict(plan['unknown'])}", "warning")
        if plan["ambiguous"]:
            send_logs(f"Auto migration ambiguous groups: {dict(plan['ambiguous'])}", "warning")

    @client.on(events.CallbackQuery(
        pattern=lambda data: data in {b"apply_auto_migrate", b"cancel_auto_migrate"}
    ))
    async def confirm_auto_migrate(event):
        sender = await event.get_sender()
        SENDER = sender.id

        if format_id(SENDER) != main_admin:
            await event.answer("Nu ai acces!", alert=True)
            return

        updates = pending_auto_migrations.pop(event.message_id, None)
        if updates is None:
            await event.answer("Migration preview expired.", alert=True)
            return

        if event.data == b"cancel_auto_migrate":
            await event.answer("Migration cancelled.")
            await client.edit_message(SENDER, event.message_id, "Academic year migration cancelled.")
            return

        await event.answer("Migrating user years...")
        await client.edit_message(SENDER, event.message_id, "Academic year migration in progress...")
        try:
            changed = db.update_user_years_from_groups(updates)
        except Exception as error:
            send_logs(f"Academic year migration failed: {error}", "error")
            await client.edit_message(
                SENDER,
                event.message_id,
                "Academic year migration failed. No partial update committed.",
            )
            return

        send_logs(f"Academic year migration completed: {changed} users updated", "info")
        await client.edit_message(
            SENDER,
            event.message_id,
            f"Academic year migration completed: {changed} users updated.",
        )

    #/admin/unadmin/list_admin/add_admin commands
    @client.on(events.NewMessage(pattern=r'^/admin$'))
    async def add_admin_command(event):
        await user_status_management(client, event, 'admin')
        return
    @client.on(events.NewMessage(pattern=r'^/unadmin$'))
    async def remove_admin_command(event):
        await user_status_management(client, event, 'unadmin')
        return
    @client.on(events.NewMessage(pattern=r'^/list_admin$'))
    async def admin_list_command(event):
        await user_status_management(client, event, 'list_admin')
        return
    
    #/ban/unban/list_ban commands
    @client.on(events.NewMessage(pattern=r'^/ban$'))
    async def ban_user_command(event):
        await user_status_management(client, event, 'ban')
        return
    @client.on(events.NewMessage(pattern=r'^/unban$'))
    async def unban_user_command(event):
        await user_status_management(client, event, 'unban')
        return
    @client.on(events.NewMessage(pattern=r'^/list_ban$'))
    async def ban_list(event):
        await user_status_management(client, event, 'list_ban')
        return

    #/update_schedule admin
    active_file_handlers = {}

    @client.on(events.NewMessage(pattern=r'^/update_schedule$'))
    async def update_schedule(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) != main_admin and f"U{SENDER}" not in contributors_df['user_id'].astype(str).tolist():
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        #select year
        text = "Select the year to update schedule:"
        buttons = [
            Button.inline("Year 1", data=b"year_1"),
            Button.inline("Year 2", data=b"year_2"),
            Button.inline("Year 3", data=b"year_3"),
            Button.inline("Year 4", data=b"year_4"),
            Button.inline("Cancel", data=b"cancel_update_schedule")
        ]
        buttons = button_grid(buttons, 2)
        await client.send_message(SENDER, text, buttons=buttons)
        send_logs(f"User {SENDER} initiated schedule update", 'info')
        return
    
    #cancel update schedule
    @client.on(events.CallbackQuery(pattern=b"cancel_update_schedule"))
    async def cancel_update_schedule(event):
        nonlocal active_file_handlers
        sender = await event.get_sender()
        SENDER = sender.id
        await event.answer("Update cancelled.")
        await client.edit_message(SENDER, event.message_id, "Schedule update cancelled.")
        
        if SENDER in active_file_handlers:
            handler_func = active_file_handlers[SENDER]
            client.remove_event_handler(handler_func)
            del active_file_handlers[SENDER]
        
        send_logs(f"User {SENDER} cancelled schedule update", 'info')
        return
    
    #year selection callback
    @client.on(events.CallbackQuery(pattern=lambda x: x.startswith(b"year_")))
    async def year_selection_callback(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) != main_admin and f"U{SENDER}" not in contributors_df['user_id'].astype(str).tolist():
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        year_selected = int(event.data.decode('utf-8').split('_')[1])
        await event.answer(f"Selected - Year {year_selected}")

        #if contributor, check if has permission for that year(multiple years possible)
        user_years = contributors_df[contributors_df['user_id'] == f"U{SENDER}"]['orar'].values
        send_logs(f"{year_selected}.  {user_years}", 'info')
        if user_years.size == 0 or year_selected not in user_years:
            await client.edit_message(SENDER, event.message_id,
                f"❌ You do not have permission to update schedule for Year {year_selected}.",
                buttons=[
                    Button.inline(f"Cancel", data=b"cancel_update_schedule")
                ]
            )
            send_logs(f"User {SENDER} tried to update schedule for Year {year_selected} without permission", 'warning')
            return
        
        await client.edit_message(SENDER, event.message_id,
            f"Selected - Year {year_selected}\n\nPlease send the new schedule file in .xlsx format:",
            buttons=[
                Button.inline(f"Cancel", data=b"cancel_update_schedule")
            ]
        )

        #file upload handler
        @client.on(events.NewMessage(from_users=SENDER))
        async def handle_schedule_file(file_event):
            # Remove the handler after first message and from tracking
            nonlocal active_file_handlers
            client.remove_event_handler(handle_schedule_file, events.NewMessage(from_users=SENDER))

            if SENDER in active_file_handlers:
                del active_file_handlers[SENDER]
            
            #if file_event is a command, ignore
            if file_event.text and file_event.text.startswith('/'):
                return

            if file_event.media and file_event.file.name and file_event.file.name.endswith('.xlsx'):
                await file_event.reply(f"File received for Year {year_selected}. Processing...")
                schedule_dir = Path("schedules")
                target = schedule_dir / f"orar{year_selected}.xlsx"
                staged = schedule_dir / f".orar{year_selected}.{file_event.id}.upload.xlsx"

                try:
                    staged.unlink(missing_ok=True)
                    await file_event.download_media(str(staged))
                    schedule, groups = load_schedule_file(staged)
                    os.replace(staged, target)
                    activate_schedule(schedule, groups, year_selected)

                    _, new_specialties, new_group_list = write_groups_to_json()
                    if new_specialties is None or new_group_list is None:
                        raise RuntimeError("group catalog refresh failed; restart required")

                    specialties.clear()
                    specialties.update(new_specialties)
                    group_list.clear()
                    group_list.update(new_group_list)
                except Exception as error:
                    send_logs(f"Schedule update failed for Year {year_selected}: {error}", "error")
                    await client.send_message(SENDER, f"Schedule update failed: {error}")
                    return
                finally:
                    staged.unlink(missing_ok=True)

                send_logs(f"Schedule for Year {year_selected} updated successfully", "info")
                await client.send_message(SENDER, f"✅ Schedule for Year {year_selected} updated successfully.")
            else:
                await file_event.reply("Please send a valid .xlsx file or type /update_schedule to start over.")
    
    #/contrib admin
    @client.on(events.NewMessage(pattern=r'^/contrib$'))
    async def show_contributors(event):
        sender = await event.get_sender()
        SENDER = sender.id

        if format_id(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        try:
            if contributors_df.empty:
                await client.send_message(SENDER, "No contributors found.", parse_mode="HTML")
                return
            
            text = "Contributors:\n\n"
            for _, row in contributors_df.iterrows():
                user_id = str(row['user_id'])[1:]
                orar = row['orar']
                text += f"<a href='tg://user?id={user_id}'>{user_id}</a> - Orar: {orar}\n"
            
            await client.send_message(SENDER, text, parse_mode="HTML")
            send_logs(f"{format_id(SENDER)} - /contrib", 'info')
        except Exception as e:
            send_logs(f"Error showing contributors: {str(e)}", 'error')
            await client.send_message(SENDER, f"Erroare la afisare contribuitori", parse_mode="HTML")

    #/holidays admin
    def _render_holiday_view():
        state = db.get_app_setting("holiday_mode", "0")
        if state == "1":
            text = "Holiday mode: <b>ON</b>\nScheduled notifications are paused."
            button = Button.inline("Turn OFF", b"holiday_set_0")
        else:
            text = "Holiday mode: <b>OFF</b>\nScheduled notifications are active."
            button = Button.inline("Turn ON", b"holiday_set_1")
        return text, [[button]]

    @client.on(events.NewMessage(pattern=r'^/holidays$'))
    async def holidays_cmd(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            send_logs(format_id(SENDER) + " - /holidays - no acces", "info")
            return
        text, buttons = _render_holiday_view()
        await client.send_message(SENDER, text, buttons=buttons, parse_mode="HTML")

    @client.on(events.CallbackQuery(pattern=rb"^holiday_set_(0|1)$"))
    async def holidays_cb(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) not in admins1:
            await event.answer("No access", alert=True)
            return
        requested = event.data.decode().rsplit("_", 1)[1]  # "0" or "1"
        try:
            db.set_app_setting("holiday_mode", requested)
        except Exception as e:
            send_logs(f"{format_id(SENDER)} - holiday_mode write FAILED: {e}", "error")
        actual = db.get_app_setting("holiday_mode", "0")
        text, buttons = _render_holiday_view()
        if actual != requested:
            text = "<b>Write failed — state unchanged.</b>\n\n" + text
        await event.edit(text, buttons=buttons, parse_mode="HTML")
        send_logs(f"{format_id(SENDER)} - holiday_mode requested={requested} actual={actual}", "info")

    #/edit_contrib admin
    @client.on(events.NewMessage(pattern=r'^/edit_contrib$'))
    async def edit_contributors(event):
        sender = await event.get_sender()
        SENDER = sender.id

        if format_id(SENDER) != main_admin:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        text = "Write the user ID(as int)"
        await client.send_message(SENDER, text)
        send_logs(f"{format_id(SENDER)} - /edit_contrib", 'info')

        @client.on(events.NewMessage(from_users=SENDER))
        async def handle_input(event):
            user_input = event.text
            # Skip if it's a command
            if user_input.startswith('/'):
                return
            try:
                remove_contrib = False
                user_id = int(user_input)
                user_str = "U" + str(user_id)
                
                contributors_df = pd.read_csv('contributors.csv')
                buttons_contrib = [
                    Button.inline("Add Contributor", data=f"add_contrib".encode()),
                    Button.inline("Remove Contributor", data=f"remove_contrib".encode()),
                    Button.inline("Cancel", data=b"cancel_contrib")
                ]

                buttons_year = [
                    Button.inline("Year 1", data=f"set_year_1".encode()),
                    Button.inline("Year 2", data=f"set_year_2".encode()),
                    Button.inline("Year 3", data=f"set_year_3".encode()),
                    Button.inline("Year 4", data=f"set_year_4".encode()),
                    Button.inline("Cancel", data=b"cancel_year")
                ]
                buttons_year = button_grid(buttons_year, 2)
                buttons_contrib = button_grid(buttons_contrib, 2)
                await client.send_message(SENDER, f"Select action for user U{user_id}:", buttons=buttons_contrib)
                client.remove_event_handler(handle_input, events.NewMessage(from_users=SENDER))

                @client.on(events.CallbackQuery(pattern=lambda x: x in [b"add_contrib", b"remove_contrib", b"cancel_contrib"]))
                async def contrib_action_callback(event):
                    sender = await event.get_sender()
                    SENDER = sender.id
                    nonlocal remove_contrib
                    remove_contrib = False
                    if event.data == b"add_contrib":
                        remove_contrib = False
                        await event.answer("Select year to set contributor:")
                        await client.edit_message(SENDER, event.message_id, f"Select year to set contributor U{user_id}:", buttons=buttons_year)
                    elif event.data == b"remove_contrib":
                        remove_contrib = True
                        await event.answer("Select year to remove contributor:")
                        await client.edit_message(SENDER, event.message_id, f"Select year to remove contributor U{user_id}:", buttons=buttons_year)
                    elif event.data == b"cancel_contrib":
                        await event.answer("Action cancelled.")
                        await client.edit_message(SENDER, event.message_id, "Action cancelled.")
                    
                    client.remove_event_handler(contrib_action_callback, events.CallbackQuery())

                @client.on(events.CallbackQuery(pattern=lambda x: x.startswith(b"set_year_")))
                async def set_year_callback(event):
                    nonlocal remove_contrib
                    global contributors_df
                    sender = await event.get_sender()
                    SENDER = sender.id
                    year_selected = int(event.data.decode('utf-8').split('_')[2])
                    
                    if remove_contrib:
                        #remove contributor
                        contributors_df = contributors_df[~((contributors_df['user_id'] == user_str) & (contributors_df['orar'] == year_selected))]
                        contributors_df.to_csv('contributors.csv', index=False)
                        await client.edit_message(SENDER, event.message_id, f"Contributor U{user_id} removed for Year {year_selected} successfully.")
                        send_logs(f"Contributor U{user_id} removed for Year {year_selected} by {SENDER}", 'info')
                    else:
                        #add contributor
                        if not ((contributors_df['user_id'] == user_str) & (contributors_df['orar'] == year_selected)).any():
                            new_row = pd.DataFrame({'user_id': [user_str], 'orar': [year_selected]})
                            contributors_df = pd.concat([contributors_df, new_row], ignore_index=True)
                            contributors_df.to_csv('contributors.csv', index=False)
                            await client.edit_message(SENDER, event.message_id, f"Contributor U{user_id} added for Year {year_selected} successfully.")
                            send_logs(f"Contributor U{user_id} added for Year {year_selected} by {SENDER}", 'info')
                        else:
                            await client.edit_message(SENDER, event.message_id, f"Contributor U{user_id} already exists for Year {year_selected}.")
                    client.remove_event_handler(set_year_callback, events.CallbackQuery())    
            except ValueError:
                await client.send_message(SENDER, "Invalid user ID! Please enter a valid integer.")
            finally:
                client.remove_event_handler(handle_input, events.NewMessage(from_users=SENDER))
