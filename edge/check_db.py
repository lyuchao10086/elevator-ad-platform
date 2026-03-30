import sqlite3
import os

db_path = "resources/edge.db"
if not os.path.exists(db_path):
    print(f"Error: {db_path} not found.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Advertisement Table ---")
cursor.execute("SELECT * FROM advertisement")
for row in cursor.fetchall():
    print(row)

print("\n--- Schedule Table ---")
cursor.execute("SELECT * FROM schedule")
for row in cursor.fetchall():
    print(row)

conn.close()
