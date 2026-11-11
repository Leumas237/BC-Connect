from pathlib import Path

from .config import settings


def supabase_enabled() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _client():
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _local_path(key: str) -> Path:
    path = settings.data_dir / "assets" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def upload_asset(key: str, content: bytes, content_type: str) -> None:
    if supabase_enabled():
        _client().storage.from_(settings.supabase_bucket).upload(
            key,
            content,
            {"content-type": content_type, "upsert": "true"},
        )
        return
    _local_path(key).write_bytes(content)


def download_asset(key: str) -> bytes:
    if supabase_enabled():
        return _client().storage.from_(settings.supabase_bucket).download(key)
    return _local_path(key).read_bytes()


def delete_asset(key: str) -> None:
    if supabase_enabled():
        _client().storage.from_(settings.supabase_bucket).remove([key])
        return
    _local_path(key).unlink(missing_ok=True)
