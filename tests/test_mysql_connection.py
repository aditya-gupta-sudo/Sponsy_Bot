import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

connection = None

try:
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )

    cursor = connection.cursor()
    cursor.execute("SELECT DATABASE(), VERSION()")

    database, version = cursor.fetchone()

    print("Connection successful")
    print("Database:", database)
    print("MySQL version:", version)

except mysql.connector.Error as error:
    print("Connection failed:", error)

finally:
    if connection and connection.is_connected():
        connection.close()