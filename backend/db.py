import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from .config import settings


SCHEMA = """
create table if not exists users (
    id integer primary key autoincrement,
    email text not null unique,
    password_hash text not null,
    password_salt text not null,
    name text not null,
    is_admin integer not null default 0,
    approved integer not null default 0,
    banned integer not null default 0,
    created_at text not null default current_timestamp,
    last_seen text not null default current_timestamp
);

create table if not exists sessions (
    token text primary key,
    user_id integer not null references users(id) on delete cascade,
    created_at text not null default current_timestamp
);
"""


def database_path():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "bc_connect.db"


def initialize_database() -> None:
    with sqlite3.connect(database_path()) as connection:
        connection.execute("pragma foreign_keys = on")
        connection.executescript(SCHEMA)


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
