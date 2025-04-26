import handlers.db as db
import logging

if __name__ == "__main__":
    # Initialize database connection
    if not db.initialize_mysql_connection():
        logging.error("Failed to establish database connection")
        exit(1)
    
    # Migrate data from CSV to MySQL
    if db.migrate_csv_to_mysql():
        logging.info("Migration completed successfully")
    else:
        logging.error("Migration failed")