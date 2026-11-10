import re
import secrets
import json
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import (
    approved_user,
    create_session,
    current_admin,
    current_user,
    hash_password,
    verify_password,
)
from .config import settings
from .db import get_db, initialize_database

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
KYI_DIR = settings.data_dir / "kyi"
MAX_KYI_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title=settings.app_name)


class RegisterPayload(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)


class LoginPayload(BaseModel):
    email: str
    password: str


class KyiDecision(BaseModel):
    approved: bool


class ProfilePayload(BaseModel):
    bio: str = Field(default="", max_length=1000)
    cycle: str = Field(default="", max_length=80)
    filiere: str = Field(default="", max_length=160)
    classe: str = Field(default="", max_length=120)
    interests: list[str] = Field(default_factory=list, max_length=12)
    intent: str = Field(default="les_deux", pattern="^(amis|couple|les_deux)$")
    age: int | None = Field(default=None, ge=15, le=80)
    instagram: str = Field(default="", max_length=160)
    snapchat: str = Field(default="", max_length=160)
    whatsapp: str = Field(default="", max_length=160)
    invisible: bool = False


class SwipePayload(BaseModel):
    target_id: int
    liked: bool


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
    with get_db() as db:
        kyi_submitted = db.execute(
            "select 1 from kyi where user_id = ?", (user["id"],)
        ).fetchone() is not None
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "is_admin": bool(user["is_admin"]),
        "approved": bool(user["approved"]),
        "kyi_submitted": kyi_submitted,
    }


@app.get("/api/profile")
def get_profile(user=Depends(current_user)):
    with get_db() as db:
        profile = db.execute("select * from profiles where user_id = ?", (user["id"],)).fetchone()
    if profile is None:
        return {
            "bio": "",
            "cycle": "",
            "filiere": "",
            "classe": "",
            "interests": [],
            "intent": "les_deux",
            "age": None,
            "instagram": "",
            "snapchat": "",
            "whatsapp": "",
            "invisible": False,
        }
    return {
        "bio": profile["bio"],
        "cycle": profile["cycle"],
        "filiere": profile["filiere"],
        "classe": profile["classe"],
        "interests": json.loads(profile["interests"]),
        "intent": profile["intent"],
        "age": profile["age"],
        "instagram": profile["instagram"],
        "snapchat": profile["snapchat"],
        "whatsapp": profile["whatsapp"],
        "invisible": bool(profile["invisible"]),
    }


@app.put("/api/profile")
def update_profile(payload: ProfilePayload, user=Depends(approved_user)):
    interests = [item.strip() for item in payload.interests if item.strip()]
    with get_db() as db:
        db.execute(
            """
            insert into profiles(user_id, bio, cycle, filiere, classe, interests, intent, age, instagram, snapchat, whatsapp, invisible)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(user_id) do update set
                bio = excluded.bio,
                cycle = excluded.cycle,
                filiere = excluded.filiere,
                classe = excluded.classe,
                interests = excluded.interests,
                intent = excluded.intent,
                age = excluded.age,
                instagram = excluded.instagram,
                snapchat = excluded.snapchat,
                whatsapp = excluded.whatsapp,
                invisible = excluded.invisible,
                updated_at = current_timestamp
            """,
            (
                user["id"],
                payload.bio.strip(),
                payload.cycle.strip(),
                payload.filiere.strip(),
                payload.classe.strip(),
                json.dumps(interests, ensure_ascii=False),
                payload.intent,
                payload.age,
                payload.instagram.strip(),
                payload.snapchat.strip(),
                payload.whatsapp.strip(),
                int(payload.invisible),
            ),
        )
    return {"ok": True}


@app.get("/api/discover")
def discover(user=Depends(approved_user)):
    with get_db() as db:
        rows = db.execute(
            """
            select u.id, u.name, p.bio, p.cycle, p.filiere, p.classe,
                   p.interests, p.intent, p.age
            from users u
            join profiles p on p.user_id = u.id
            where u.id != ?
              and u.approved = 1
              and u.banned = 0
              and p.invisible = 0
              and not exists (
                  select 1 from swipes s
                  where s.swiper_id = ? and s.target_id = u.id
              )
            order by u.last_seen desc, u.id desc
            limit 30
            """,
            (user["id"], user["id"]),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "bio": row["bio"],
            "cycle": row["cycle"],
            "filiere": row["filiere"],
            "classe": row["classe"],
            "interests": json.loads(row["interests"]),
            "intent": row["intent"],
            "age": row["age"],
        }
        for row in rows
    ]


@app.post("/api/swipe")
def swipe(payload: SwipePayload, user=Depends(approved_user)):
    if payload.target_id == user["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas sélectionner ton propre profil.")
    with get_db() as db:
        target = db.execute(
            "select id from users where id = ? and approved = 1 and banned = 0",
            (payload.target_id,),
        ).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Profil indisponible.")
        db.execute(
            """
            insert into swipes(swiper_id, target_id, liked)
            values (?, ?, ?)
            on conflict(swiper_id, target_id) do update set liked = excluded.liked,
            created_at = current_timestamp
            """,
            (user["id"], payload.target_id, int(payload.liked)),
        )
        matched = False
        if payload.liked:
            reciprocal = db.execute(
                """
                select 1 from swipes
                where swiper_id = ? and target_id = ? and liked = 1
                """,
                (payload.target_id, user["id"]),
            ).fetchone()
            if reciprocal:
                user_a, user_b = sorted((user["id"], payload.target_id))
                db.execute(
                    "insert or ignore into matches(user_a, user_b) values (?, ?)",
                    (user_a, user_b),
                )
                matched = True
    return {"ok": True, "matched": matched}


@app.get("/api/matches")
def matches(user=Depends(approved_user)):
    with get_db() as db:
        rows = db.execute(
            """
            select u.id, u.name, p.bio, p.cycle, p.filiere, p.classe,
                   p.instagram, p.snapchat, p.whatsapp, m.created_at
            from matches m
            join users u on u.id = case when m.user_a = ? then m.user_b else m.user_a end
            left join profiles p on p.user_id = u.id
            where m.user_a = ? or m.user_b = ?
            order by m.created_at desc
            """,
            (user["id"], user["id"], user["id"]),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/kyi", status_code=status.HTTP_201_CREATED)
async def submit_kyi(
    full_name: str = Form(..., min_length=2, max_length=160),
    birthdate: str = Form(...),
    classe: str = Form(..., min_length=1, max_length=120),
    card: UploadFile = File(...),
    user=Depends(current_user),
):
    if card.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="La carte doit être une image JPG, PNG ou WEBP.")
    content = await card.read(MAX_KYI_SIZE + 1)
    if len(content) > MAX_KYI_SIZE:
        raise HTTPException(status_code=413, detail="La carte ne doit pas dépasser 5 Mo.")
    if not content:
        raise HTTPException(status_code=400, detail="Le fichier de carte est vide.")

    KYI_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(card.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    filename = f"{user['id']}-{secrets.token_hex(12)}{suffix}"
    destination = KYI_DIR / filename
    destination.write_bytes(content)

    with get_db() as db:
        previous = db.execute("select card_path from kyi where user_id = ?", (user["id"],)).fetchone()
        db.execute(
            """
            insert into kyi(user_id, full_name, birthdate, classe, card_path)
            values (?, ?, ?, ?, ?)
            on conflict(user_id) do update set
                full_name = excluded.full_name,
                birthdate = excluded.birthdate,
                classe = excluded.classe,
                card_path = excluded.card_path,
                submitted_at = current_timestamp
            """,
            (user["id"], full_name.strip(), birthdate.strip(), classe.strip(), filename),
        )
    if previous and previous["card_path"] != filename:
        old_file = KYI_DIR / previous["card_path"]
        if old_file.exists():
            old_file.unlink()
    return {"ok": True, "kyi_submitted": True}


@app.get("/api/admin/kyi")
def pending_kyi(user=Depends(current_admin)):
    with get_db() as db:
        rows = db.execute(
            """
            select k.user_id, k.full_name, k.birthdate, k.classe, k.submitted_at, u.email
            from kyi k join users u on u.id = k.user_id
            where u.approved = 0 and u.banned = 0
            order by k.submitted_at asc
            """
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/admin/kyi/{user_id}/decision")
def decide_kyi(user_id: int, payload: KyiDecision, user=Depends(current_admin)):
    with get_db() as db:
        target = db.execute("select id from users where id = ?", (user_id,)).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
        if payload.approved:
            db.execute("update users set approved = 1 where id = ?", (user_id,))
        else:
            db.execute("delete from users where id = ?", (user_id,))
    if not payload.approved:
        card_files = list(KYI_DIR.glob(f"{user_id}-*"))
        for card_file in card_files:
            card_file.unlink(missing_ok=True)
    return {"ok": True, "approved": payload.approved}


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
