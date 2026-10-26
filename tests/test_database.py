import sqlite3

import pytest

from app.database import Database


def test_failed_write_rolls_back_and_all_connections_close(tmp_path, monkeypatch):
    connections = []
    connect = sqlite3.connect

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            return super().close()

    def tracked(path):
        connection = connect(path, factory=TrackedConnection)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked)
    db = Database(tmp_path / "failure.db")
    db.initialize()
    with db._connect() as connection:
        connection.execute(
            "CREATE TRIGGER reject_action BEFORE INSERT ON action_items "
            "BEGIN SELECT RAISE(ABORT,'fixture failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.save_action_item("owner/repo", "Not saved", "high")
    assert db.list_action_items() == []
    with db._connect() as connection:
        connection.execute("DROP TRIGGER reject_action")
    db.save_action_item("owner/repo", "Saved once", "high")
    assert db.overview()["open_actions"] == 1
    assert all(c.closed for c in connections)
