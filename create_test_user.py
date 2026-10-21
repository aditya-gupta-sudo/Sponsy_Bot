
from getpass import getpass

import mysql.connector
from pwdlib import PasswordHash
from dotenv import load_dotenv
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

email = "aditya.test@example.com"
password = getpass("Enter a temporary test password: ")

password_hash = PasswordHash.recommended().hash(password)

connection = mysql.connector.connect(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME", "sponsybot"),
)

try:
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO users (name, email, password_hash, role)
        VALUES (%s, %s, %s, %s)
        """,
        ("Aditya Test", email, password_hash, "NAIVE_USER"),
    )
    connection.commit()
    print("Test user created. User ID:", cursor.lastrowid)

finally:
    connection.close()
