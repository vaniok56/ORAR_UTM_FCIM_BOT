import asyncio
import pandas as pd
import numpy as np
import datetime
import pytz
import os
import glob

from telethon import TelegramClient, events, types
from telethon.tl.custom import Button

import handlers.db as db
from functions import button_grid, send_logs, print_next_course, is_rate_limited, format_id, process_schedule_file

moldova_tz = pytz.timezone('Europe/Chisinau')

current_year = 26  # (+1 each year)
main_admin = "U500303890"  # Your user ID here as string

def register_admin_handlers(client, admins1, admins2):
    #/admin_help admin
    @client.on(events.NewMessage(pattern=r'^/admin_help$'))
    async def admin_help(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if format_id(SENDER) not in admins1 and format_id(SENDER) not in admins2:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        text = "Admin commands:\n\n"
        text += "/stats - show statistics\n\n"
        text += "/backup - manual database backup\n\n"
        text += "/use_backup - restore database from backup\n\n"
        text += "/message - send a message to users\n\n"
        text += "/debug_next - debug print next course\n\n"
        #text += "/new_year - update all users' year(+1)\n\n"
        text += "Change user status:\n"
        text += "/ban - ban a user\n"
        text += "/unban - unban a user\n"
        text += "/list_ban - show banned users\n\n"
        text += "/admin - add a user as admin\n"
        text += "/unadmin - remove admin privileges\n"
        text += "/list_admin - show admin users\n\n"
        text += "/update_schedule - update schedule from file\n\n"
        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /admin_help", 'info')
        return
    
    #/stats admin
    @client.on(events.NewMessage(pattern=r'^/stats$'))
    async def statsss(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
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
        
        text += f"📈 Summary:\n"
        text += f"  • Total users: {total_users}\n"
        text += f"  • Total users with groups: {users_with_groups_count}\n"
        text += f"  • Users with notifications: {users_with_notifications}\n"
        text += f"  • Users with selected sub-group: {users_with_subgroups}\n"
            
        await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /stats", "info")

    #/message admin
    @client.on(events.NewMessage(pattern=r'^/message$'))
    async def message_command(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        if "U" + str(SENDER) not in admins1:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        text = "Select the recipient:"
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
        buttons = button_grid(buttons, 2)
        await client.send_message(SENDER, text, buttons=buttons)

    #message callback
    @client.on(events.CallbackQuery(pattern=lambda x: x.startswith(b"to")))
    async def message_callback(event):
        sender = await event.get_sender()
        SENDER = sender.id
        data = event.data.decode('utf-8')
        
        if not data.startswith("to"):
            return
        global to_who, useridd, when, text, input_step, media_path
        useridd = 0
        to_who = int(data[2])
        input_step = 1
        media_path = None
        recipient_dict = {
            1: "Myself",
            2: "TI-241",
            3: "Notifon users",
            4: "A user",
            5: "All users",
            6: "Year 1",
            7: "Year 2",
            8: "Year 3",
            9: "Year 4"
        }
        await event.answer()
        await client.edit_message(SENDER, event.message_id, "Selected: " + recipient_dict.get(to_who))
        if to_who == 4:
            await client.send_message(SENDER, "Please enter the user ID(as int):")
        else:
            input_step = 2
            await client.send_message(SENDER, "Please enter the time in HH:MM format or \"Now\":")

        @client.on(events.NewMessage(from_users=SENDER))
        async def handle_input(event):
            global input_step, useridd, when, text, media_path
            user_input = event.text

            if input_step == 1 and to_who == 4:
                useridd = int(user_input)
                input_step = 2
                await client.send_message(SENDER, "Please enter the time in HH:MM format or \"Now\":")
            elif input_step == 2:
                when = user_input
                input_step = 3
                await client.send_message(SENDER, "Send your message (text or attach image/file with caption):")
            elif input_step == 3:
                # Check if there's media attached
                has_media = event.media is not None
                
                if has_media:
                    try:
                        # Download the media
                        timestamp = datetime.datetime.now(moldova_tz).strftime("%Y%m%d_%H%M%S")
                        sender_id = str(SENDER)[-6:]  # Last 6 digits of sender ID
                        filename = f"message_{timestamp}_{sender_id}"
                        media_path = await event.download_media(f"temp/{filename}")
                        text = event.text  # Caption becomes the text
                    except Exception as e:
                        send_logs(f"Error downloading media: {e}", 'error')
                        await client.send_message(SENDER, f"Error with media: {e}")
                        return
                else:
                    text = user_input
                    media_path = None
                
                client.remove_event_handler(handle_input, events.NewMessage(from_users=SENDER))

                summary = f"\nSend to: {recipient_dict.get(to_who)}"
                if useridd != 0:
                    summary += f"\nUser ID: {useridd}"
                summary += f"\nTime: {when}"
                
                if media_path:
                    summary += f"\nMessage with media: \n{text}"
                else:
                    summary += f"\nMessage: \n{text}"
                
                await client.send_message(SENDER, summary)
                
                buttons = button_grid([Button.inline("Yes", data=b"send_mess_yes"), Button.inline("No", data=b"send_mess_no")], 2)
                await client.send_message(SENDER, "Send the message?", buttons=buttons)

                @client.on(events.CallbackQuery(pattern=lambda x: x in [b"send_mess_yes", b"send_mess_no"]))
                async def confirmation_callback(event):
                    global to_who, when, useridd, text, media_path
                    sender = await event.get_sender()
                    SENDER = sender.id
                    if event.data == b"send_mess_yes":
                        try:
                            await event.answer("Scheduling message...")
                            await client.edit_message(SENDER, event.message_id, "Message scheduled successfully!")
                            await send_mess(to_who, when, useridd)
                        except Exception as e:
                            send_logs(f"Error confirmation_callback(yes): {e}", 'error')
                    elif event.data == b"send_mess_no":
                        try:
                            await event.answer("Canceling...")
                            await client.edit_message(SENDER, event.message_id, "Message sending canceled.")
                            # Clean up media file if exists
                            if media_path and os.path.exists(media_path):
                                os.remove(media_path)
                                send_logs(f"Removed temp file: {media_path}", 'info')
                        except Exception as e:
                            send_logs(f"Error confirmation_callback(no): {e}", 'error')
                    client.remove_event_handler(confirmation_callback, events.CallbackQuery())

    #send the custom message
    async def send_mess(to_who, when, useridd):
        global text, media_path
        
        now = datetime.datetime.now(moldova_tz).time()
        current_time = datetime.datetime.strptime(str(now)[:-7], "%H:%M:%S")
        if when == "Now":
            scheduled = current_time
        else:
            scheduled = datetime.datetime.strptime(when, "%H:%M")
        
        try:
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
                return
                
            if len(all_users) == 0:
                send_logs("No users found to send message to", 'warning')
                return
        except Exception as e:
            send_logs(f"Error retrieving users for message: {e}", 'error')
            return
            
        if when != "Now":
            send_logs("waiting to send a message - " + str(scheduled - current_time), 'info')
            await asyncio.sleep((scheduled - current_time).total_seconds())
            
        for _, row in all_users.iterrows():
            user = row['SENDER']
            sender = int(user[1:])
            try:
                if media_path and os.path.exists(media_path):
                    # Send with media
                    await client.send_file(
                        sender,
                        media_path,
                        caption=text,
                        parse_mode="Markdown"
                    )
                else:
                    # Send text only
                    await client.send_message(sender, text, parse_mode="Markdown")
                send_logs("Send successful to " + user, 'info')
            except Exception as e:
                send_logs(f"Error sending message to {str(sender)}: {e}", 'error')
        
        # Clean up after sending
        if media_path and os.path.exists(media_path):
            os.remove(media_path)
            send_logs(f"Removed temp file: {media_path}", 'info')

    #/debug_next admin
    @client.on(events.NewMessage(pattern=r'^/debug_next$'))
    async def debugg(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        subgrupa = db.locate_field("U"+str(event.sender_id), 'subgrupa')
        if "U"+str(event.sender_id) not in admins1:
            await client.send_message(event.sender_id, "Nu ai acces!", parse_mode="HTML")
            return
        
        week_day = int((datetime.datetime.now(moldova_tz)).weekday())
        is_even = (datetime.datetime.now(moldova_tz)).isocalendar().week % 2
        for i in range(1, 8):
            text = "Perechea urmatore: #" + str(i)
            text += print_next_course(week_day, 'TI-241', is_even, i, subgrupa)
            if text:
                await client.send_message(SENDER, text, parse_mode="HTML")
        send_logs(format_id(SENDER) + " - /debug_next", 'info')
    
    #/backup admin
    @client.on(events.NewMessage(pattern=r'^/backup$'))
    async def manual_backup(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
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
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
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
        if is_rate_limited(SENDER):
            send_logs(f"Rate limited user: {SENDER}", 'warning')
            return
        
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
            del user_action_waiting[SENDER]
            return
    
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
        global backup_to_restore
        backup_to_restore = None
        await client.edit_message(SENDER, event.message_id, "Database restoration cancelled.")
        send_logs(f"User {SENDER} cancelled database restore", 'info')

    @client.on(events.CallbackQuery(pattern=lambda x: x.startswith(b"backup_")))
    async def backup_selection_callback(event):
        nonlocal backup_to_restore
        sender = await event.get_sender()
        SENDER = sender.id
        
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

    #/new_year admin
    @client.on(events.NewMessage(pattern=r'^/new_year$'))
    async def new_year(event):
        sender = await event.get_sender()
        SENDER = sender.id
        if format_id(SENDER) != main_admin:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        #1 year passed
        #update all users year_n field
        await client.send_message(SENDER,
                f"⚠️ WARNING: This will update all users' year by +1\n\nDo you want to continue?",
                buttons=[
                    [Button.inline("Yes, update years", data=b"confirm_update_years")],
                    [Button.inline("Cancel", data=b"cancel_update_years")]
                ])

    @client.on(events.CallbackQuery(pattern=b"confirm_update_years"))
    async def confirm_update_years(event):
        sender = await event.get_sender()
        SENDER = sender.id

        await event.answer("Updating user years...")
        await client.edit_message(SENDER, event.message_id, "Updating user years...")

        if db.update_user_years():
            await client.edit_message(SENDER, event.message_id, "All users' year has been updated successfully.")
            send_logs("All users' year has been updated successfully.", 'info')
        else:
            await client.edit_message(SENDER, event.message_id, "Failed to update user years.")
            send_logs("Failed to update user years.", 'error')

    @client.on(events.CallbackQuery(pattern=b"cancel_update_years"))
    async def cancel_update_years(event):
        sender = await event.get_sender()
        SENDER = sender.id

        await event.answer("Update cancelled.")
        await client.edit_message(SENDER, event.message_id, "Update cancelled.")
        send_logs("User cancelled update user years.", 'info')

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
        if format_id(SENDER) != main_admin:
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
        if format_id(SENDER) != main_admin:
            await client.send_message(SENDER, "Nu ai acces!", parse_mode="HTML")
            return
        
        year_selected = int(event.data.decode('utf-8').split('_')[1])
        await event.answer(f"Selected - Year {year_selected}")
        
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
            
            if file_event.media and hasattr(file_event.media, 'document') and file_event.file.name.endswith('.xlsx'):
                await file_event.reply(f"File received for Year {year_selected}. Processing...")
                # Download the file
                file_path = await file_event.download_media(f"temp/schedule_year_{year_selected}.xlsx")
                send_logs(f"User {SENDER} uploaded schedule for Year {year_selected}", 'info')
                
                # Process the schedule file
                try:
                    if process_schedule_file(f"temp/schedule_year_{year_selected}.xlsx", year_selected):
                        await client.send_message(SENDER, f"✅ Schedule for Year {year_selected} updated successfully.")
                        send_logs(f"Schedule for Year {year_selected} updated successfully.", 'info')
                    else:
                        await client.send_message(SENDER, f"❌ Failed to update schedule for Year {year_selected}. Check the file format.")
                        send_logs(f"Failed to update schedule for Year {year_selected}.", 'error')
                except Exception as e:
                    send_logs(f"Error processing schedule for Year {year_selected}: {str(e)}", 'error')
                    await client.send_message(SENDER, f"Error processing schedule: {str(e)}")
                
                # Replace the old schedule file
                try:
                    import shutil
                    shutil.copy2(f"../temp/schedule_year_{year_selected}.xlsx", f"../schedules/orar{year_selected}.xlsx")
                    os.remove(f"../temp/schedule_year_{year_selected}.xlsx")  # Clean up temp file after copying
                    send_logs(f"Replaced old schedule file for Year {year_selected}", 'info')
                    await client.send_message(SENDER, f"Old schedule file for Year {year_selected} replaced successfully.")
                except Exception as e:
                    send_logs(f"Error replacing schedule file for Year {year_selected}: {str(e)}", 'error')
                    await client.send_message(SENDER, f"Error replacing schedule file: {str(e)}")
            else:
                await file_event.reply("Please send a valid .xlsx file or type /update_schedule to start over.")
        
    
            