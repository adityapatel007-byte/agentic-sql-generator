"""SQL safety layer — the single most important defense. Must be watertight."""
from __future__ import annotations

import pytest

from app.db.safety import UnsafeSQLError, assert_read_only


class TestAllowedQueries:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT 1",
            "SELECT * FROM customers",
            "SELECT c.name, SUM(o.total) FROM customers c JOIN orders o ON o.customer_id = c.id GROUP BY c.name",
            "WITH top_customers AS (SELECT customer_id, SUM(total) t FROM orders GROUP BY customer_id) "
            "SELECT * FROM top_customers WHERE t > 100",
            "SELECT * FROM orders UNION SELECT * FROM orders",
        ],
    )
    def test_select_variants_allowed(self, sql: str):
        assert assert_read_only(sql)


class TestBlockedQueries:
    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO customers (name) VALUES ('mallory')",
            "UPDATE customers SET name = 'x'",
            "DELETE FROM customers",
            "DROP TABLE customers",
            "CREATE TABLE foo (id INT)",
            "ALTER TABLE customers ADD COLUMN evil TEXT",
            "TRUNCATE TABLE customers",
            "ATTACH DATABASE '/tmp/evil.db' AS evil",
            "PRAGMA writable_schema = 1",
            "VACUUM",
        ],
    )
    def test_writes_and_ddl_rejected(self, sql: str):
        with pytest.raises(UnsafeSQLError):
            assert_read_only(sql)

    def test_multi_statement_rejected(self):
        with pytest.raises(UnsafeSQLError):
            assert_read_only("SELECT 1; DROP TABLE customers")

    def test_empty_rejected(self):
        with pytest.raises(UnsafeSQLError):
            assert_read_only("")
