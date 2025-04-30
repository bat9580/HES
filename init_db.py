import sqlite3

DATABASE = "dcu_connections.db"

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS dcu_connections (
    dcu_number TEXT PRIMARY KEY,
    ip_address TEXT,
    first_connection TEXT,
    last_connection TEXT,
    access_time INTEGER
)
""")

conn.commit()
conn.close()

print("✅ Database initialized!")
