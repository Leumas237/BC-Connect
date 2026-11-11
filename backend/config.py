import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str
    data_dir: Path
    database_url: str
    supabase_url: str
    supabase_service_role_key: str
    supabase_bucket: str
    admin_emails: frozenset[str]
    daily_likes: int
    spam_strikes_ban: int


def _csv(value: str) -> frozenset[str]:
    return frozenset(item.strip().lower() for item in value.split(",") if item.strip())


settings = Settings(
    app_name=os.getenv("BC_APP_NAME", "BC Connect"),
    data_dir=Path(os.getenv("BC_DATA_DIR", "data")),
    database_url=os.getenv("BC_DATABASE_URL", ""),
    supabase_url=os.getenv("SUPABASE_URL", ""),
    supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
    supabase_bucket=os.getenv("SUPABASE_STORAGE_BUCKET", "bc-connect"),
    admin_emails=_csv(os.getenv("BC_ADMIN_EMAILS", "")),
    daily_likes=int(os.getenv("BC_DAILY_LIKES", "15")),
    spam_strikes_ban=int(os.getenv("BC_SPAM_STRIKES_BAN", "30")),
)
