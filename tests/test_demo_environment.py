"""Tests for demo/setup_demo_environment.py (real SQLite, no Agentiva API)."""

from __future__ import annotations

import sqlite3

from demo.setup_demo_environment import setup_demo_db


def test_setup_demo_db_creates_customers_and_transactions(tmp_path) -> None:
    db = tmp_path / "t.db"
    path = setup_demo_db(str(db))
    assert path == str(db)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM customers")
    assert cur.fetchone()[0] == 100
    cur.execute("SELECT COUNT(*) FROM transactions")
    assert cur.fetchone()[0] == 50
    conn.close()
