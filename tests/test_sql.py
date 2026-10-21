
import sqlite3

connection = sqlite3.connect("sponsybot.db")

# Enable foreign-key enforcement for this connection
connection.execute("PRAGMA foreign_keys = ON")

cursor = connection.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY,
        event_name TEXT NOT NULL,
        college TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT,
        event_date TEXT
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        company_id INTEGER PRIMARY KEY,
        company_name TEXT NOT NULL,
        website TEXT,
        industry TEXT
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS event_companies (
        event_id INTEGER NOT NULL,
        company_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        score REAL,
        human_rank INTEGER,
        status TEXT NOT NULL DEFAULT 'discovered',

        PRIMARY KEY (event_id, company_id),

        FOREIGN KEY (event_id)
            REFERENCES events(event_id),

        FOREIGN KEY (company_id)
            REFERENCES companies(company_id)
    )
""")


cursor.executemany("""
    INSERT INTO companies (company_name, website, industry)
    VALUES (?, ?, ?)
""", [
    ("Microsoft", "https://www.microsoft.com", "Technology"),
    ("Google", "https://www.google.com", "Technology"),
    ("Adobe", "https://www.adobe.com", "Software"),
    ("GitHub", "https://github.com", "Developer Tools"),
    ("Razorpay", "https://razorpay.com", "Fintech"),
    ("Red Bull", "https://www.redbull.com", "Beverages"),
    ("Deloitte", "https://www.deloitte.com", "Consulting"),
    ("Tata Consultancy Services", "https://www.tcs.com", "IT Services"),
    ("NVIDIA", "https://www.nvidia.com", "Semiconductors and AI"),
    ("Amazon Web Services", "https://aws.amazon.com", "Cloud Computing")
])

connection.commit()

print("Sample companies inserted successfully!")


connection.commit()

print("\nAll three tables are ready.")

cursor.execute("SELECT * FROM events")
print("\n events:", cursor.fetchall())
cursor.execute("SELECT * FROM companies")
print("\n companies:", cursor.fetchall())
cursor.execute("SELECT * FROM event_companies")
print("\n event_companies", cursor.fetchall())

connection.close()
