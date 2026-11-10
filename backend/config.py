import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str
    data_dir: Path
    admin_emails: frozenset[str]


def _csv(value: str) -> frozenset[str]:
    return frozenset(item.strip().lower() for item in value.split(",") if item.strip())


settings = Settings(
    app_name=os.getenv("BC_APP_NAME", "BC Connect"),
    data_dir=Path(os.getenv("BC_DATA_DIR", "data")),
    admin_emails=_csv(os.getenv("BC_ADMIN_EMAILS", "")),
)
