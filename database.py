import sqlite3
from config import DB_NAME

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY,
            group_name TEXT,
            added_by INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users VALUES (?,?,?)', 
                   (user_id, username, first_name))
    conn.commit()
    conn.close()

def add_group(group_id, group_name, added_by):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO groups VALUES (?,?,?)', 
                   (group_id, group_name, added_by))
    conn.commit()
    conn.close()

def get_all_groups():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT group_id FROM groups')
    groups = cursor.fetchall()
    conn.close()
    return [g[0] for g in groups]