import re
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import create_session, current_user, hash_password, verify_password
from .config import settings
from .db import get_db, initialize_database

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title=settings.app_name)


class RegisterPayload(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)


class LoginPayload(BaseModel):
    email: str
    password: str


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.get("/api/health")
def health():
    return {"ok": True, "app_name": settings.app_name}


@app.get("/api/config")
def public_config():
    return {"app_name": settings.app_name}


@app.post("/api/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterPayload):
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Adresse email invalide.")
    password_hash, password_salt = hash_password(payload.password)
    is_admin = int(email in settings.admin_emails)
    with get_db() as db:
        try:
            cursor = db.execute(
                """
                insert into users(email, password_hash, password_salt, name, is_admin, approved)
                values (?, ?, ?, ?, ?, ?)
                """,
                (email, password_hash, password_salt, payload.name.strip(), is_admin, is_admin),
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status_code=409, detail="Cette adresse est déjà inscrite.") from exc
            raise
        user_id = cursor.lastrowid
    return {"token": create_session(user_id), "user_id": user_id}


@app.post("/api/login")
def login(payload: LoginPayload):
    email = payload.email.strip().lower()
    with get_db() as db:
        user = db.execute("select * from users where email = ?", (email,)).fetchone()
        if user is not None:
            db.execute("update users set last_seen = current_timestamp where id = ?", (user["id"],))
    if user is None or not verify_password(payload.password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect.")
    if user["banned"]:
        raise HTTPException(status_code=403, detail="Compte suspendu.")
    return {"token": create_session(user["id"]), "user_id": user["id"]}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "is_admin": bool(user["is_admin"]),
        "approved": bool(user["approved"]),
    }


@app.post("/api/logout")
def logout(request: Request, user=Depends(current_user)):
    token = request.headers["authorization"].split(" ", 1)[1]
    with get_db() as db:
        db.execute("delete from sessions where token = ?", (token,))
    return {"ok": True}


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/{path:path}")
def frontend(path: str):
    requested = FRONTEND_DIR / path
    if path and requested.is_file():
        return FileResponse(requested)
    return FileResponse(FRONTEND_DIR / "index.html")
