#!/usr/bin/env python3
"""
Database Migration Script untuk Ayo Fokus Log Synchronization (MySQL Version)
Jalankan script ini untuk mengupdate database yang sudah ada ke skema terbaru.
"""

import mysql.connector
import os
import datetime
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# MySQL Configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "ayo_fokus")

def get_mysql_connection():
    """Establishes and returns a MySQL database connection."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            autocommit=False # Manage transactions manually
        )
        return conn
    except mysql.connector.Error as err:
        logging.error(f"MySQL connection error: {err}")
        print(f"Error: Could not connect to MySQL database '{DB_NAME}'. Please check your connection details and ensure the database exists.")
        print(f"Details: Host={DB_HOST}, User={DB_USER}, DB={DB_NAME}")
        sys.exit(1) # Exit if connection fails

def migrate_database():
    """Migrate existing database to support log synchronization"""
    
    print("Memulai migrasi database untuk log synchronization (MySQL)...")
    
    conn = None
    try:
        conn = get_mysql_connection()
        c = conn.cursor(dictionary=True) # Use dictionary=True for fetching results as dicts
        
        # --- Backup existing data (MySQL equivalent) ---
        # MySQL doesn't have a direct "CREATE TABLE AS SELECT" with IF NOT EXISTS for backup
        # A more robust backup strategy would involve dumping the database or specific tables.
        # For this script, we'll just log a message about manual backup.
        print("Penting: Untuk backup data, disarankan melakukan dump database MySQL secara manual.")
        print("Misalnya: mysqldump -u [user] -p [database_name] > backup.sql")
        
        # Check if columns already exist in monitoring_logs
        c.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{DB_NAME}' AND TABLE_NAME='monitoring_logs'")
        existing_monitoring_columns = [column['COLUMN_NAME'] for column in c.fetchall()]
        
        # Add new columns to monitoring_logs if they don't exist
        new_monitoring_columns = [
            ('message', 'TEXT'),
            ('source', 'VARCHAR(50) DEFAULT "web"'),
            ('sync_id', 'VARCHAR(255)'),
            ('original_timestamp', 'VARCHAR(255)'),
            ('session_id', 'VARCHAR(255)')
        ]
        
        for column_name, column_def in new_monitoring_columns:
            if column_name not in existing_monitoring_columns:
                alter_query = f"ALTER TABLE monitoring_logs ADD COLUMN {column_name} {column_def}"
                print(f"Menambah kolom ke monitoring_logs: {column_name}")
                c.execute(alter_query)
            else:
                print(f"Kolom '{column_name}' sudah ada di monitoring_logs, dilewati.")

        # Check if session_id column exists in student_status
        c.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{DB_NAME}' AND TABLE_NAME='student_status'")
        existing_student_status_columns = [column['COLUMN_NAME'] for column in c.fetchall()]
        if 'session_id' not in existing_student_status_columns:
            print("Menambah kolom 'session_id' ke student_status...")
            c.execute("ALTER TABLE student_status ADD COLUMN session_id VARCHAR(255)")
        else:
            print("Kolom 'session_id' sudah ada di student_status, dilewati.")
        
        # Create sync_status table
        print("Membuat tabel sync_status (jika belum ada)...")
        c.execute(f'''
            CREATE TABLE IF NOT EXISTS sync_status (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT,
                class_id INT,
                last_frontend_sync TIMESTAMP NULL,
                last_backend_update TIMESTAMP NULL,
                sync_lag_seconds INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes (id) ON DELETE CASCADE
            )
        ''')
        print("Tabel sync_status dipastikan ada.")
        
        # Create indexes for better performance
        print("Membuat indexes untuk performance (jika belum ada)...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_monitoring_logs_timestamp ON monitoring_logs(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_monitoring_logs_student_class ON monitoring_logs(student_id, class_id)",
            "CREATE INDEX IF NOT EXISTS idx_monitoring_logs_source ON monitoring_logs(source)",
            "CREATE INDEX IF NOT EXISTS idx_sync_status_student_class ON sync_status(student_id, class_id)",
            "CREATE INDEX IF NOT EXISTS idx_student_status_student_class ON student_status(student_id, class_id)"
        ]
        
        for index_query in indexes:
            try:
                c.execute(index_query)
                print(f"   - Index dipastikan: {index_query.split('ON')[0].replace('CREATE INDEX IF NOT EXISTS ', '')}")
            except mysql.connector.Error as err:
                # MySQL's CREATE INDEX IF NOT EXISTS only works for unique indexes in some versions
                # For non-unique, it might throw an error if index exists.
                # We'll just log and continue if it's an "index already exists" error.
                if "Duplicate key name" in str(err) or "index already exists" in str(err).lower():
                    print(f"   - Index sudah ada, dilewati: {index_query.split('ON')[0].replace('CREATE INDEX IF NOT EXISTS ', '')}")
                else:
                    raise # Re-raise other errors

        # Create synchronized monitoring view
        print("Membuat view untuk synchronized monitoring (jika belum ada)...")
        # Drop existing view if it exists to ensure it's recreated with the latest schema
        c.execute("DROP VIEW IF EXISTS synchronized_monitoring_view")
        c.execute('''
            CREATE VIEW synchronized_monitoring_view AS
            SELECT 
                m.id,
                u.username,
                c.name as class_name,
                m.event_type,
                m.message,
                m.source,
                m.session_id,
                m.timestamp,
                m.original_timestamp,
                s.is_in_meet as current_status,
                s.last_activity
            FROM monitoring_logs m
            JOIN users u ON m.student_id = u.id
            JOIN classes c ON m.class_id = c.id
            LEFT JOIN student_status s ON m.student_id = s.student_id AND m.class_id = s.class_id
            ORDER BY m.timestamp DESC
        ''')
        print("View synchronized_monitoring_view dipastikan ada.")
        
        # Update existing records to have proper source and message
        print("Mengupdate data existing (source dan message)...")
        c.execute("UPDATE monitoring_logs SET source = 'web' WHERE source IS NULL")
        c.execute("UPDATE monitoring_logs SET message = event_type WHERE message IS NULL OR message = ''")
        print("Data monitoring_logs diupdate.")
        
        conn.commit()
        print("Migrasi database berhasil!")
        
        # Show migration summary
        c.execute("SELECT COUNT(*) FROM monitoring_logs")
        log_count = c.fetchone()['COUNT(*)']
        
        c.execute("SELECT COUNT(DISTINCT source) FROM monitoring_logs WHERE source IS NOT NULL")
        source_count = c.fetchone()['COUNT(DISTINCT source)']
        
        print(f"\nSummary migrasi:")
        print(f"   Total monitoring logs: {log_count}")
        print(f"   Jumlah source berbeda: {source_count}")
        print(f"   Backup tables: Disarankan backup manual MySQL.")
        print(f"   New tables: sync_status")
        print(f"   New view: synchronized_monitoring_view")
        
        return True
        
    except mysql.connector.Error as e:
        print(f"Error during migration: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            c.close()
            conn.close()

def verify_migration():
    """Verify that migration was successful"""
    print("\nVerifying migration...")
    
    conn = None
    try:
        conn = get_mysql_connection()
        c = conn.cursor(dictionary=True) # Use dictionary=True for fetching results as dicts
        
        # Check if new columns exist in monitoring_logs
        c.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{DB_NAME}' AND TABLE_NAME='monitoring_logs'")
        monitoring_columns = [column['COLUMN_NAME'] for column in c.fetchall()]
        required_monitoring_columns = ['message', 'source', 'sync_id', 'original_timestamp', 'session_id']
        missing_monitoring_columns = [col for col in required_monitoring_columns if col not in monitoring_columns]
        
        if missing_monitoring_columns:
            print(f"Missing columns in monitoring_logs: {missing_monitoring_columns}")
            return False

        # Check if session_id column exists in student_status
        c.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{DB_NAME}' AND TABLE_NAME='student_status'")
        student_status_columns = [column['COLUMN_NAME'] for column in c.fetchall()]
        if 'session_id' not in student_status_columns:
            print("'session_id' column not found in student_status table!")
            return False
        
        # Check if sync_status table exists
        c.execute(f"SHOW TABLES LIKE 'sync_status'")
        if not c.fetchone():
            print("sync_status table tidak ditemukan!")
            return False
        
        # Check if view exists
        c.execute(f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA = '{DB_NAME}' AND TABLE_NAME='synchronized_monitoring_view'")
        if not c.fetchone():
            print("synchronized_monitoring_view tidak ditemukan!")
            return False
        
        print("Migrasi terverifikasi berhasil!")
        return True
        
    except mysql.connector.Error as e:
        print(f"Error during verification: {e}")
        return False
    finally:
        if conn:
            c.close()
            conn.close()

def rollback_migration():
    """Rollback migration if needed (Note: MySQL rollback is more complex than SQLite)"""
    print("\nRolling back migration (MySQL)...")
    print("Penting: Rollback di MySQL untuk perubahan skema lebih kompleks.")
    print("Disarankan untuk merestore dari backup database yang dibuat sebelum migrasi.")
    print("Script ini hanya akan menghapus tabel dan view yang baru dibuat.")
    
    conn = None
    try:
        conn = get_mysql_connection()
        c = conn.cursor()
        
        # Remove new tables and views
        print("Menghapus tabel sync_status...")
        c.execute("DROP TABLE IF EXISTS sync_status")
        print("Menghapus view synchronized_monitoring_view...")
        c.execute("DROP VIEW IF EXISTS synchronized_monitoring_view")
        
        # Removing columns is generally not recommended in a simple rollback script
        # as it can lead to data loss. Manual intervention is usually preferred.
        print("Rollback kolom 'message', 'source', 'sync_id', 'original_timestamp', 'session_id' di monitoring_logs")
        print("dan 'session_id' di student_status memerlukan langkah manual jika diperlukan.")
        print("Contoh: ALTER TABLE monitoring_logs DROP COLUMN message;")

        conn.commit()
        print("Rollback selesai (penghapusan tabel/view baru)!")
        
    except mysql.connector.Error as e:
        print(f"Error during rollback: {e}")
    finally:
        if conn:
            c.close()
            conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Ayo Fokus - Database Migration untuk Log Synchronization (MySQL)")
    print("=" * 60)
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migration()
    else:
        success = migrate_database()
        if success:
            verify_migration()
            print("\nDatabase siap untuk log synchronization!")
            print("\nLangkah selanjutnya:")
            print("1. Pastikan semua file aplikasi sudah diupdate.")
            print("2. Jalankan launcher.py atau start_ayo_fokus.bat.")
        else:
            print("\nJika terjadi masalah, jalankan:")
            print("   python database_migration.py rollback")
