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
    spam_strikes integer not null default 0,
    policy_accepted_at text,
    created_at text not null default current_timestamp,
    last_seen text not null default current_timestamp
);

create table if not exists sessions (
    token text primary key,
    user_id integer not null references users(id) on delete cascade,
    created_at text not null default current_timestamp
);

create table if not exists kyi (
    user_id integer primary key references users(id) on delete cascade,
    full_name text not null,
    birthdate text not null,
    classe text not null,
    card_path text not null,
    submitted_at text not null default current_timestamp
);

create table if not exists profiles (
    user_id integer primary key references users(id) on delete cascade,
    bio text not null default '',
    cycle text not null default '',
    filiere text not null default '',
    classe text not null default '',
    interests text not null default '[]',
    intent text not null default 'les_deux',
    age integer,
    instagram text not null default '',
    snapchat text not null default '',
    whatsapp text not null default '',
    invisible integer not null default 0,
    updated_at text not null default current_timestamp
);

create table if not exists swipes (
    swiper_id integer not null references users(id) on delete cascade,
    target_id integer not null references users(id) on delete cascade,
    liked integer not null,
    created_at text not null default current_timestamp,
    primary key (swiper_id, target_id),
    check (swiper_id != target_id)
);

create table if not exists matches (
    user_a integer not null references users(id) on delete cascade,
    user_b integer not null references users(id) on delete cascade,
    created_at text not null default current_timestamp,
    primary key (user_a, user_b),
    check (user_a < user_b)
);

create table if not exists reports (
    id integer primary key autoincrement,
    reporter_id integer not null references users(id) on delete cascade,
    reported_id integer not null references users(id) on delete cascade,
    reason text not null,
    status text not null default 'pending',
    created_at text not null default current_timestamp
);

create table if not exists photos (
    id integer primary key autoincrement,
    user_id integer not null references users(id) on delete cascade,
    filename text not null,
    content_type text not null,
    created_at text not null default current_timestamp
);

create table if not exists push_subs (
    endpoint text primary key,
    user_id integer not null references users(id) on delete cascade,
    subscription_json text not null,
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
        profile_columns = {
            row[1] for row in connection.execute("pragma table_info(profiles)").fetchall()
        }
        for column in ("instagram", "snapchat", "whatsapp"):
            if column not in profile_columns:
                connection.execute(
                    f"alter table profiles add column {column} text not null default ''"
                )
        user_columns = {
            row[1] for row in connection.execute("pragma table_info(users)").fetchall()
        }
        if "spam_strikes" not in user_columns:
            connection.execute(
                "alter table users add column spam_strikes integer not null default 0"
            )
        if "policy_accepted_at" not in user_columns:
            connection.execute("alter table users add column policy_accepted_at text")


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
