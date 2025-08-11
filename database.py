import sqlite3

# Connect to your SQLite DB
conn = sqlite3.connect("connection.db")
cursor = conn.cursor()

# Run the query
cursor.execute("PRAGMA table_info(installed_meters);")

# Fetch and print the result
columns = cursor.fetchall()
for col in columns:
    print(col)

# Close connection when done
conn.close()
