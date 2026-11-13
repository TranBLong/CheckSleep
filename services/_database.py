"""Shared SQL Server transaction and row helpers for services."""

from contextlib import contextmanager

from db.connection import get_connection


@contextmanager
def transaction(connection_factory=None):
    connection = (connection_factory or get_connection)()
    try:
        import pyodbc

        try:
            with connection:
                yield connection
        except pyodbc.Error as exc:
            from db.connection import DatabaseError

            raise DatabaseError("Lỗi khi thực hiện thao tác SQL Server.") from exc
    finally:
        connection.close()


def row_as_dict(cursor, row):
    if row is None:
        return None
    return {
        column[0]: value
        for column, value in zip(cursor.description, row)
    }


def rows_as_dicts(cursor, rows):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]
