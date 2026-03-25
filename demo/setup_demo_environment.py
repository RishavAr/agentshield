"""
Sets up a real demo environment with actual data and services.

Creates a SQLite database with realistic (fake) customer records and transactions.
Run once before `real_agent.py`:

    python demo/setup_demo_environment.py
"""

from __future__ import annotations

import os
import sqlite3

from faker import Faker

fake = Faker()


def setup_demo_db(db_path: str | None = None) -> str:
    """Create a real SQLite database with 100 fake customer records."""
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "demo.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            ssn TEXT,
            credit_card TEXT,
            cvv TEXT,
            address TEXT,
            medical_record_id TEXT,
            diagnosis TEXT,
            prescription TEXT,
            date_of_birth TEXT,
            account_balance REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            amount REAL,
            recipient TEXT,
            type TEXT,
            status TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            user TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute("DELETE FROM transactions")
    cursor.execute("DELETE FROM customers")
    cursor.execute("DELETE FROM audit_log")
    conn.commit()

    # Insert 100 realistic customer records
    for _ in range(100):
        cursor.execute(
            """
            INSERT INTO customers (name, email, phone, ssn, credit_card, cvv,
                                   address, medical_record_id, diagnosis, prescription,
                                   date_of_birth, account_balance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fake.name(),
                fake.email(),
                fake.phone_number(),
                fake.ssn(),
                fake.credit_card_number(),
                fake.credit_card_security_code(),
                fake.address().replace("\n", ", "),
                f"MRN-{fake.random_int(min=10000000, max=99999999)}",
                fake.random_element(
                    [
                        "Diabetes Type 2",
                        "Hypertension",
                        "Asthma",
                        "Depression",
                        "Arthritis",
                        "None",
                    ]
                ),
                fake.random_element(
                    [
                        "Metformin 500mg",
                        "Lisinopril 10mg",
                        "Albuterol inhaler",
                        "Sertraline 50mg",
                        "None",
                    ]
                ),
                fake.date_of_birth(minimum_age=18, maximum_age=85).isoformat(),
                round(fake.pyfloat(min_value=100, max_value=50000), 2),
            ),
        )

    # Insert sample transactions
    for _ in range(50):
        cursor.execute(
            """
            INSERT INTO transactions (customer_id, amount, recipient, type, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                fake.random_int(min=1, max=100),
                round(fake.pyfloat(min_value=10, max_value=5000), 2),
                fake.company(),
                fake.random_element(["payment", "refund", "transfer", "withdrawal"]),
                fake.random_element(["completed", "pending", "failed"]),
            ),
        )

    conn.commit()
    conn.close()
    print(f"Demo database created at {db_path} with 100 customers and 50 transactions")
    return db_path


if __name__ == "__main__":
    setup_demo_db()
