import mysql.connector
import pandas as pd
import time
import datetime
import pytz
import os
from contextlib import contextmanager
from functions import send_logs

moldova_tz = pytz.timezone('Europe/Chisinau')
time_zone = pytz.timezone('Europe/Chisinau')

# Connection pool
pool = None
MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds
user_data_cache = {}

def initialize_mysql_connection():
    """Initialize MySQL connection pool with retry logic"""
    global pool, _cached_all_users_df

    # Initialize cached users dataframe if not already set
    if '_cached_all_users_df' not in globals():
        _cached_all_users_df = pd.DataFrame()
    
    # Close existing pool if it exists
    if pool is not None:
        try:
            pool._remove_connections()
        except:
            pass

    # Get MySQL connection details from environment
    config = {
        'host': os.environ.get('MYSQL_HOST', 'mysql'),
        'user': os.environ.get('MYSQL_USER'),
        'password': os.environ.get('MYSQL_PASSWORD'),
        'database': os.environ.get('MYSQL_DATABASE'),
        'pool_reset_session': True,
        'autocommit': True,
        'connection_timeout': 30,
        'pool_size': 32,  # Increase from 20 to handle more concurrent connections
        'pool_name': f"orar_pool_{int(time.time())}"  # Unique pool name each time
    }
    
    # Print connection parameters for debugging
    send_logs(f"Attempting MySQL connection to {config['host']} as {config['user']}", "info")
    
    for attempt in range(MAX_RETRIES):
        try:
            # Create connection pool
            pool = mysql.connector.pooling.MySQLConnectionPool(
                **config
            )
            
            # Test connection by getting one from the pool
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()
                send_logs(f"Connected to MySQL version: {version[0]}", "info")
            
            # refresh cache with new data if possible
            try:
                load_user_cache()
            except:
                send_logs("Failed to preload user cache, will use existing cache if available", "warning")
                
            send_logs("MySQL connection established successfully", "info")
            return True
        except mysql.connector.Error as err:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                send_logs(f"MySQL connection attempt {attempt+1} failed: {err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to initialize MySQL connection after {MAX_RETRIES} attempts: {str(err)}", "error")
                return False
        except Exception as e:
            send_logs(f"Unexpected error initializing MySQL: {str(e)}", "error")
            return False

def load_user_cache():
    """Preload user cache from database"""
    global _cached_all_users_df
    
    with get_db_connection() as conn:
        cursor = conn.cursor(dictionary=True, buffered=True)
        results_iter = cursor.execute('CALL get_all_users()', multi=True)
        
        for result_set in results_iter:
            if result_set.with_rows:
                result = result_set.fetchall()
                if result:
                    df = pd.DataFrame(result)
                    _cached_all_users_df = df
                    for row in result:
                        user_data_cache[row['SENDER']] = row
                    send_logs(f"Preloaded {len(df)} users into cache", "info")
                break
        
        while cursor.nextset():
            pass

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        # Get a connection from the pool
        for attempt in range(3):  # Try up to 3 times
            try:
                if pool is None:
                    raise Exception("Connection pool not initialized")
                conn = pool.get_connection()
                break
            except mysql.connector.errors.PoolError as pool_err:
                send_logs(f"Pool error: {pool_err}. Attempting to reinitialize pool...", "warning")
                initialize_mysql_connection()
                time.sleep(1)
            except mysql.connector.Error as err:
                send_logs(f"DB connection attempt {attempt+1} failed: {err}. Retrying...", "warning")
                time.sleep(0.5)  # in seconds
        
        if not conn:
            raise Exception("Could not establish database connection after retries")
            
        yield conn
    except Exception as e:
        send_logs(f"Database connection error: {str(e)}", "error")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as close_err:
                send_logs(f"Error closing connection: {close_err}", "warning")

def save_dataframe(df):
    """Save DataFrame to database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Begin transaction
            conn.start_transaction()
            
            success_count = 0
            error_count = 0
            
            for idx, row in df.iterrows():
                try:
                    cursor.execute('''
                    CALL migrate(
                        %s, %s, %s, %s, 
                        %s, %s, %s, %s, 
                        %s, %s, %s, %s
                    )
                    ''', 
                    (
                        row['SENDER'],
                        row['group'],
                        row['spec'],
                        row['year'],
                        row['subgrupa'],
                        row['noti'],
                        row['admin'],
                        row['prem'],
                        row['gamble'],
                        row['ban'],
                        row['ban_time'],
                        row['last_cmd'],
                    ))  # Removed multi=True
                    
                    # Process all result sets
                    while True:
                        try:
                            cursor.fetchall()
                            if not cursor.nextset():
                                break
                        except mysql.connector.Error as fetch_err:
                            # Some statements might not return results
                            break
                            
                    success_count += 1
                    
                    # Log progress periodically
                    if success_count % 50 == 0:
                        send_logs(f"Processed {success_count} rows", "info")
                        
                except mysql.connector.Error as row_err:
                    error_count += 1
                    send_logs(f"Error on row {idx} (SENDER: {row['SENDER']}): {str(row_err)}", "error")
                    # Continue with other rows
            
            # Commit only if we had some successful inserts
            if success_count > 0:
                conn.commit()
                send_logs(f"Committed {success_count} rows, {error_count} errors", "info")
                return success_count > 0
            else:
                conn.rollback()
                send_logs("No rows inserted successfully, rolling back", "error")
                return False
                
    except mysql.connector.Error as e:
        send_logs(f"MySQL error in save_dataframe: {str(e)}", "error")
        return False
    except Exception as e:
        send_logs(f"Failed to save DataFrame: {str(e)}", "error")
        return False

def update_user_field(sender_id, field, value):
    """Update a specific field for a user"""
    for attempt in range(MAX_RETRIES):
        try:                
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                
                cursor.callproc('update_field', [sender_id, field, value])
                conn.commit()
                
                # Process results from stored procedure
                result_found = False
                for result_set in cursor.stored_results():
                    result = result_set.fetchall()
                    result_found = True
                    break
                
                # Use consistent cache key format for invalidation
                if sender_id in user_data_cache:
                    del user_data_cache[sender_id]
                
                return True
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in update_user_field (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                if sender_id in user_data_cache:
                    del user_data_cache[sender_id]
                send_logs(f"Failed to update user field {field} for {sender_id} after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                return False
        except Exception as e:
            if sender_id in user_data_cache:
                del user_data_cache[sender_id]
            send_logs(f"Failed to update user field: {str(e)}", "error")
            return False

def add_new_user(sender_id):
    """Add a new user to the database"""
    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(buffered=True)
                
                cursor.callproc('add_new_user', [sender_id])
                
                user_id = None
                # Process each result set from stored procedure
                for result_set in cursor.stored_results():
                    user_data = result_set.fetchone()
                    if user_data and user_data[0]:
                        user_id = user_data[0]
                        break
                
                conn.commit()
                
                # Verify user was actually created
                cursor.execute("SELECT 1 FROM users WHERE SENDER = %s", (sender_id,))
                user_exists = cursor.fetchone() is not None
                
                if user_id and user_exists:
                    send_logs(f"User {sender_id} added successfully with ID: {user_id}", "info")
                    return True
                else:
                    send_logs(f"User {sender_id} failed to be added or verify - ID: {user_id}, Exists: {user_exists}", "error")
                    return False
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in add_new_user (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to add new user after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                return False
        except Exception as e:
            send_logs(f"Failed to add new user: {str(e)}", "error")
            return False

def create_mysql_backup(backup_path):
    """Create a MySQL database backup using mysqldump"""
    for attempt in range(MAX_RETRIES):
        try:
            # Use the same credentials as the connection pool
            host = os.environ.get('MYSQL_HOST', 'mysql')
            user = os.environ.get('MYSQL_USER')
            password = os.environ.get('MYSQL_PASSWORD')
            database = os.environ.get('MYSQL_DATABASE')
            
            # Create mysqldump command
            command = f"mysqldump -h {host} -u {user} -p'{password}' {database} > {backup_path}"
            
            # Execute command
            send_logs(f"Creating MySQL backup at {backup_path}", "info")
            os.system(command)
            
            if os.path.exists(backup_path):
                send_logs(f"MySQL backup created successfully: {os.path.getsize(backup_path)} bytes", "info")
                return True
            else:
                send_logs(f"MySQL backup file not created", "error")
                return False
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in create_mysql_backup (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to create MySQL backup after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                return False
        except Exception as e:
            send_logs(f"Failed to create database backup: {str(e)}", "error")
            return False

def migrate_csv_to_mysql(csv_path="BD.csv"):
    """Migrate data from CSV file to MySQL"""
    try:
        # Load data from CSV
        df = pd.read_csv(csv_path)
        send_logs(f"Loaded {len(df)} records from CSV", "info")
        
        # Save to MySQL
        success = save_dataframe(df)
        
        if success:
            send_logs("CSV data successfully migrated to MySQL", "info")
        else:
            send_logs("Failed to migrate CSV data to MySQL", "error")
            
        return success
    except Exception as e:
        send_logs(f"CSV migration failed: {str(e)}", "error")
        return False
    
def locate_field(sender_id, field):
    """Locate a specific field for a user with retry logic"""    
    if sender_id in user_data_cache and user_data_cache[sender_id] is not None:
        return user_data_cache[sender_id].get(field)

    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                
                cursor.callproc('select_all_user_data', [sender_id])
                
                all_user_data = {}
                for result_set in cursor.stored_results():
                    row = result_set.fetchone()
                    if row:
                        all_user_data = row
                        break
                
                # Only cache non-empty results
                if all_user_data:
                    user_data_cache[sender_id] = all_user_data
                    
                    # Return the specific field requested
                    field_value = all_user_data.get(field)
                    send_logs(f"locate_field({sender_id}, {field}) returned: {field_value}", "debug")
                    return field_value
                else:
                    send_logs(f"No data found for user {sender_id}", "warning")
                    return None
                
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)  # Exponential backoff
                send_logs(f"DB error in locate_field (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to locate field {field} for {sender_id} after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                return None
        except Exception as e:
            send_logs(f"Failed to locate field {field} for {sender_id}: {str(e)}", "error")
            return None

def get_admins(rank):
    """Get all admins from the database"""
    for attempt in range(MAX_RETRIES):   
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.callproc('get_admins', [rank])
                
                admins = []
                # Process each result set from stored procedure
                for result_set in cursor.stored_results():
                    rows = result_set.fetchall()
                    if rows:
                        admins = [row[0] for row in rows]
                        break
                
                if admins:
                    send_logs(f"Admins rank [{rank}] retrieved: {admins}", "info")
                    return admins
                else:
                    send_logs("No admins found", "info")
                    return []
                    
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in get_admins (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to get admins after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                return []
        except Exception as e:
            send_logs(f"Failed to get admins: {str(e)}", "error")
            return []
    
def get_user_count():
    """Get the total number of users in the database"""
    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.callproc('get_user_count')
                
                count = 0
                for result_set in cursor.stored_results():
                    row = result_set.fetchone()
                    if row:
                        count = row[0]
                        break
                
                return count
                
        except mysql.connector.Error as db_err:
            # Error handling remains the same
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in get_user_count (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to get user count after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                return 0
        except Exception as e:
            send_logs(f"Failed to get user count: {str(e)}", "error")
            return 0
    
def get_all_users():
    """Get all users from the database as a pandas DataFrame"""
    # Try to use cached data if available when DB is down
    global _cached_all_users_df
    
    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)
                
                cursor.callproc('get_all_users')
                
                # Process each result set
                result = None
                for result_set in cursor.stored_results():
                    result = result_set.fetchall()
                    break
                    
                # Convert list of dictionaries to DataFrame and save cache
                if result:
                    df = pd.DataFrame(result)
                    # Update both individual user cache and full dataframe cache
                    for row in result:
                        user_data_cache[row['SENDER']] = row
                    _cached_all_users_df = df.copy()  # Store a complete copy
                    send_logs(f"All users retrieved: {df.shape[0]} rows", "info")
                    return df
                else:
                    # Check if we have cached data before returning empty
                    if '_cached_all_users_df' in globals() and not _cached_all_users_df.empty:
                        send_logs("No users found in fresh query, using cached data", "warning")
                        return _cached_all_users_df
                    
                    send_logs("No users found", "info")
                    return pd.DataFrame(columns=[
                        'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                        'admins', 'prem', 'subgrupa', 'gamble', 
                        'ban', 'ban_time', 'last_cmd'
                    ])
                    
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in get_all_users (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to get all users after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                
                # Return cached data if available instead of empty dataframe
                if '_cached_all_users_df' in globals() and not _cached_all_users_df.empty:
                    send_logs(f"Using cached user data ({len(_cached_all_users_df)} records) due to DB failure", "warning")
                    return _cached_all_users_df
                
                return pd.DataFrame(columns=[
                    'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                    'admins', 'prem', 'subgrupa', 'gamble', 
                    'ban', 'ban_time', 'last_cmd'
                ])
        except Exception as e:
            send_logs(f"Failed to get all users: {str(e)}", "error")
            
            # Return cached data if available
            if '_cached_all_users_df' in globals() and not _cached_all_users_df.empty:
                send_logs(f"Using cached user data ({len(_cached_all_users_df)} records) due to error", "warning")
                return _cached_all_users_df
                
            return pd.DataFrame(columns=[
                'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                'admins', 'prem', 'subgrupa', 'gamble', 
                'ban', 'ban_time', 'last_cmd'
            ])

def get_all_users_with(field, value):
    """Get all users with a specific field and value"""    
    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)
                
                cursor.callproc('get_all_users_with', [field, value])
                
                result = None
                # Process each result set from stored procedure
                for result_set in cursor.stored_results():
                    result = result_set.fetchall()
                    break
                    
                if result:
                    df = pd.DataFrame(result)
                    return df
                else:
                    send_logs("No users found", "info")
                    return pd.DataFrame(columns=[
                        'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                        'admins', 'prem', 'subgrupa', 'gamble', 
                        'ban', 'ban_time', 'last_cmd'
                    ])
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)  # Exponential backoff
                send_logs(f"DB error in get_all_users_with (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to get all users with {field}={value}: {str(db_err)}", "error")
                # Return empty DataFrame if all attempts fail
                return pd.DataFrame(columns=[
                    'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                    'admins', 'prem', 'subgrupa', 'gamble', 
                    'ban', 'ban_time', 'last_cmd'
                ])
        except Exception as e:
            send_logs(f"Failed to get all users with {field}={value}: {str(e)}", "error")
            return pd.DataFrame(columns=[
                'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                'admins', 'prem', 'subgrupa', 'gamble', 
                'ban', 'ban_time', 'last_cmd'
            ])

def get_all_users_without(field, value):
    """Get all users without a specific field and value"""    
    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor(dictionary=True, buffered=True)
                
                cursor.callproc('get_all_users_without', [field, value])
                
                result = None
                # Process each result set from stored procedure
                for result_set in cursor.stored_results():
                    result = result_set.fetchall()
                    break
                    
                if result:
                    df = pd.DataFrame(result)
                    return df
                else:
                    send_logs("No users found", "info")
                    return pd.DataFrame(columns=[
                        'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                        'admins', 'prem', 'subgrupa', 'gamble', 
                        'ban', 'ban_time', 'last_cmd'
                    ])
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)  # Exponential backoff
                send_logs(f"DB error in get_all_users_without (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to get all users without {field}={value}: {str(db_err)}", "error")
                # Return empty DataFrame if all attempts fail
                return pd.DataFrame(columns=[
                    'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                    'admins', 'prem', 'subgrupa', 'gamble', 
                    'ban', 'ban_time', 'last_cmd'
                ])
        except Exception as e:
            send_logs(f"Failed to get all users without {field}={value}: {str(e)}", "error")
            return pd.DataFrame(columns=[
                'id', 'SENDER', 'group_n', 'spec', 'year_s', 'noti', 
                'admins', 'prem', 'subgrupa', 'gamble', 
                'ban', 'ban_time', 'last_cmd'
            ])
        
def is_user_exists(sender_id):
    """Check if a user exists in the database"""
    if sender_id in user_data_cache:
        send_logs(f"User {sender_id} exists in the database(from cache)", "info")
        return True
    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                sql = "SELECT is_user_exists(%s) AS exists_flag"
                cursor.execute(sql, (sender_id,))
                result = cursor.fetchone()
                exists = result[0] == 1 if result else False
                
                if exists:
                    send_logs(f"User {sender_id} exists in the database", "info")
                    return True
                else:
                    send_logs(f"User {sender_id} does not exist in the database", "info")
                    return False
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in is_user_exists (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to check if user exists: {str(db_err)}", "error")
                return False
        except Exception as e:
            send_logs(f"Failed to check if user exists: {str(e)}", "error")
            return False

def restore_backup(backup_path):
    """Use a MySQL backup file to restore the database"""
    for attempt in range(MAX_RETRIES):
        try:
            host = os.environ.get('MYSQL_HOST', 'mysql')
            user = os.environ.get('MYSQL_USER')
            password = os.environ.get('MYSQL_PASSWORD')
            database = os.environ.get('MYSQL_DATABASE')
            
            command = f"mysql -h {host} -u {user} -p'{password}' {database} < {backup_path}"
            send_logs(f"Restoring MySQL database from backup at {backup_path}", "info")
            os.system(command)
            send_logs("MySQL database restored successfully", "info")
            return True
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in use_backup (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to restore MySQL database after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                return False
        except Exception as e:
            send_logs(f"Failed to restore MySQL database: {str(e)}", "error")
            return False        

def update_user_years():
    """Increment the year of all users by 1"""
    for attempt in range(MAX_RETRIES):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.callproc('update_user_years')
                conn.commit()
                
                # Clear the entire user cache since years have changed
                user_data_cache.clear()
                
                send_logs("All users' year has been updated successfully", "info")
                return True
        except mysql.connector.Error as db_err:
            if attempt < MAX_RETRIES - 1:
                delay = 0.5 * (2 ** attempt)
                send_logs(f"DB error in update_user_years (attempt {attempt+1}/{MAX_RETRIES}): {db_err}. Retrying in {delay}s...", "warning")
                time.sleep(delay)
            else:
                send_logs(f"Failed to update user years after {MAX_RETRIES} attempts: {str(db_err)}", "error")
                return False
        except Exception as e:
            send_logs(f"Failed to update user years: {str(e)}", "error")
            return False