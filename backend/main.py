import asyncio
import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, status
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
UPLOADS_DIR = settings.data_dir / "uploads"
MAX_KYI_SIZE = 5 * 1024 * 1024
MAX_PHOTO_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
active_sockets: dict[int, set[WebSocket]] = {}
main_loop: asyncio.AbstractEventLoop | None = None

app = FastAPI(title=settings.app_name)


async def notify_user(user_id: int, event: dict) -> None:
    sockets = list(active_sockets.get(user_id, set()))
    for socket in sockets:
        try:
            await socket.send_json(event)
        except Exception:
            active_sockets.get(user_id, set()).discard(socket)


def current_daily_likes(db, user_id: int) -> int:
    row = db.execute(
        """
        select count(*) as count from swipes
        where swiper_id = ? and liked = 1 and date(created_at) = date('now')
        """,
        (user_id,),
    ).fetchone()
    return int(row["count"])


def send_push(user_id: int, payload: dict) -> None:
    private_key = os.getenv("BC_VAPID_PRIVATE_KEY", "")
    claims_email = os.getenv("BC_VAPID_CLAIMS_EMAIL", "")
    if not private_key or not claims_email:
        return
    from pywebpush import WebPushException, webpush

    with get_db() as db:
        subscriptions = db.execute(
            "select endpoint, subscription_json from push_subs where user_id = ?",
            (user_id,),
        ).fetchall()
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=json.loads(subscription["subscription_json"]),
                data=json.dumps(payload),
                vapid_private_key=private_key,
                vapid_claims={"sub": claims_email},
            )
        except WebPushException as error:
            if getattr(error, "response", None) is not None and error.response.status_code in (404, 410):
                with get_db() as db:
                    db.execute("delete from push_subs where endpoint = ?", (subscription["endpoint"],))


class RegisterPayload(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)
    privacy_accepted: bool


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


class ReportPayload(BaseModel):
    target_id: int
    reason: str = Field(min_length=3, max_length=1000)


class ReportDecision(BaseModel):
    action: str = Field(pattern="^(ban|dismiss)$")


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict[str, str] = Field(default_factory=dict)


class DeleteAccountPayload(BaseModel):
    password: str


@app.on_event("startup")
async def startup() -> None:
    global main_loop
    main_loop = asyncio.get_running_loop()
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
    if not payload.privacy_accepted:
        raise HTTPException(status_code=400, detail="La politique de confidentialité doit être acceptée.")
    password_hash, password_salt = hash_password(payload.password)
    is_admin = int(email in settings.admin_emails)
    with get_db() as db:
        try:
            cursor = db.execute(
                """
                insert into users(
                    email, password_hash, password_salt, name, is_admin, approved, policy_accepted_at
                )
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email,
                    password_hash,
                    password_salt,
                    payload.name.strip(),
                    is_admin,
                    is_admin,
                    datetime.utcnow().isoformat(),
                ),
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
        daily_likes = current_daily_likes(db, user["id"])
        photos = db.execute(
            "select id from photos where user_id = ? order by id", (user["id"],)
        ).fetchall()
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "is_admin": bool(user["is_admin"]),
        "approved": bool(user["approved"]),
        "kyi_submitted": kyi_submitted,
        "daily_likes": daily_likes,
        "daily_like_limit": settings.daily_likes,
        "photos": [{"id": photo["id"]} for photo in photos],
    }


@app.get("/api/profile")
def get_profile(user=Depends(current_user)):
    with get_db() as db:
        profile = db.execute("select * from profiles where user_id = ?", (user["id"],)).fetchone()
        photos = db.execute(
            "select id from photos where user_id = ? order by id", (user["id"],)
        ).fetchall()
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
            "photos": [{"id": photo["id"]} for photo in photos],
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
        "photos": [{"id": photo["id"]} for photo in photos],
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


@app.post("/api/profile/photo", status_code=status.HTTP_201_CREATED)
async def upload_profile_photo(
    photo: UploadFile = File(...),
    user=Depends(approved_user),
):
    if photo.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="La photo doit être une image JPG, PNG ou WEBP.")
    content = await photo.read(MAX_PHOTO_SIZE + 1)
    if len(content) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=413, detail="La photo ne doit pas dépasser 5 Mo.")
    with get_db() as db:
        count = db.execute(
            "select count(*) as count from photos where user_id = ?", (user["id"],)
        ).fetchone()["count"]
        if count >= 6:
            raise HTTPException(status_code=400, detail="Un profil ne peut pas contenir plus de 6 photos.")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(photo.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    filename = f"{user['id']}-{secrets.token_hex(12)}{suffix}"
    (UPLOADS_DIR / filename).write_bytes(content)
    with get_db() as db:
        cursor = db.execute(
            "insert into photos(user_id, filename, content_type) values (?, ?, ?)",
            (user["id"], filename, photo.content_type),
        )
    return {"id": cursor.lastrowid}


@app.delete("/api/profile/photos/{photo_id}")
def delete_profile_photo(photo_id: int, user=Depends(approved_user)):
    with get_db() as db:
        photo = db.execute(
            "select filename from photos where id = ? and user_id = ?",
            (photo_id, user["id"]),
        ).fetchone()
        if photo is None:
            raise HTTPException(status_code=404, detail="Photo introuvable.")
        db.execute("delete from photos where id = ?", (photo_id,))
    path = UPLOADS_DIR / photo["filename"]
    path.unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/profile/photo/{photo_id}")
def get_profile_photo(photo_id: int, user=Depends(approved_user)):
    from fastapi.responses import FileResponse

    with get_db() as db:
        photo = db.execute(
            """
            select p.filename, p.content_type, p.user_id
            from photos p
            join users u on u.id = p.user_id
            where p.id = ? and u.approved = 1 and u.banned = 0
            """,
            (photo_id,),
        ).fetchone()
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo introuvable.")
    return FileResponse(UPLOADS_DIR / photo["filename"], media_type=photo["content_type"])


@app.get("/api/discover")
def discover(user=Depends(approved_user)):
    with get_db() as db:
        rows = db.execute(
            """
            select u.id, u.name, p.bio, p.cycle, p.filiere, p.classe,
                   p.interests, p.intent, p.age,
                   (select id from photos where user_id = u.id order by id limit 1) as photo_id
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
            "photo_id": row["photo_id"],
        }
        for row in rows
    ]


@app.post("/api/swipe")
def swipe(payload: SwipePayload, user=Depends(approved_user)):
    if payload.target_id == user["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas sélectionner ton propre profil.")
    matched = False
    with get_db() as db:
        target = db.execute(
            "select id from users where id = ? and approved = 1 and banned = 0",
            (payload.target_id,),
        ).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Profil indisponible.")
        if payload.liked and current_daily_likes(db, user["id"]) >= settings.daily_likes:
            db.execute("update users set spam_strikes = spam_strikes + 1 where id = ?", (user["id"],))
            strikes = db.execute(
                "select spam_strikes from users where id = ?", (user["id"],)
            ).fetchone()["spam_strikes"]
            if strikes >= settings.spam_strikes_ban:
                db.execute("update users set banned = 1 where id = ?", (user["id"],))
                db.execute("delete from sessions where user_id = ?", (user["id"],))
            quota_message = (
                "Compte suspendu pour dépassement répété du quota."
                if strikes >= settings.spam_strikes_ban
                else f"Quota quotidien atteint ({settings.daily_likes} likes)."
            )
        else:
            quota_message = ""
        if quota_message:
            return {"ok": False, "matched": False, "quota_exceeded": True, "message": quota_message}
        db.execute(
            """
            insert into swipes(swiper_id, target_id, liked)
            values (?, ?, ?)
            on conflict(swiper_id, target_id) do update set liked = excluded.liked,
            created_at = current_timestamp
            """,
            (user["id"], payload.target_id, int(payload.liked)),
        )
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
    if matched and main_loop is not None:
        asyncio.create_task(notify_user(payload.target_id, {"type": "match"}))
        asyncio.create_task(
            asyncio.to_thread(
                send_push,
                payload.target_id,
                {"title": "BC Connect", "body": "C’est un match !"},
            )
        )
    return {"ok": True, "matched": matched}


@app.get("/api/matches")
def matches(user=Depends(approved_user)):
    with get_db() as db:
        rows = db.execute(
            """
            select u.id, u.name, p.bio, p.cycle, p.filiere, p.classe,
                   p.instagram, p.snapchat, p.whatsapp,
                   (select id from photos where user_id = u.id order by id limit 1) as photo_id,
                   m.created_at
            from matches m
            join users u on u.id = case when m.user_a = ? then m.user_b else m.user_a end
            left join profiles p on p.user_id = u.id
            where m.user_a = ? or m.user_b = ?
            order by m.created_at desc
            """,
            (user["id"], user["id"], user["id"]),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/report", status_code=status.HTTP_201_CREATED)
def report(payload: ReportPayload, user=Depends(approved_user)):
    if payload.target_id == user["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas te signaler toi-même.")
    with get_db() as db:
        user_a, user_b = sorted((user["id"], payload.target_id))
        existing_match = db.execute(
            "select 1 from matches where user_a = ? and user_b = ?",
            (user_a, user_b),
        ).fetchone()
        if existing_match is None:
            raise HTTPException(status_code=403, detail="Un signalement est possible après un match.")
        db.execute(
            "insert into reports(reporter_id, reported_id, reason) values (?, ?, ?)",
            (user["id"], payload.target_id, payload.reason.strip()),
        )
        db.execute("delete from matches where user_a = ? and user_b = ?", (user_a, user_b))
        db.execute(
            """
            insert into swipes(swiper_id, target_id, liked) values (?, ?, 0)
            on conflict(swiper_id, target_id) do update set liked = 0
            """,
            (user["id"], payload.target_id),
        )
        db.execute(
            """
            insert into swipes(swiper_id, target_id, liked) values (?, ?, 0)
            on conflict(swiper_id, target_id) do update set liked = 0
            """,
            (payload.target_id, user["id"]),
        )
    return {"ok": True}


@app.get("/api/admin/reports")
def admin_reports(user=Depends(current_admin)):
    with get_db() as db:
        rows = db.execute(
            """
            select r.id, r.reason, r.status, r.created_at,
                   reporter.email as reporter_email, reported.email as reported_email
            from reports r
            join users reporter on reporter.id = r.reporter_id
            join users reported on reported.id = r.reported_id
            order by case when r.status = 'pending' then 0 else 1 end, r.created_at desc
            """
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/admin/reports/{report_id}")
def decide_report(report_id: int, payload: ReportDecision, user=Depends(current_admin)):
    with get_db() as db:
        report_row = db.execute(
            "select reported_id from reports where id = ?", (report_id,)
        ).fetchone()
        if report_row is None:
            raise HTTPException(status_code=404, detail="Signalement introuvable.")
        if payload.action == "ban":
            db.execute("update users set banned = 1 where id = ?", (report_row["reported_id"],))
            db.execute("delete from sessions where user_id = ?", (report_row["reported_id"],))
            db.execute("update reports set status = 'banned' where id = ?", (report_id,))
        else:
            db.execute("update reports set status = 'dismissed' where id = ?", (report_id,))
    return {"ok": True, "status": "banned" if payload.action == "ban" else "dismissed"}


@app.get("/api/account/export")
def export_account(user=Depends(current_user)):
    with get_db() as db:
        profile = db.execute("select * from profiles where user_id = ?", (user["id"],)).fetchone()
        kyi = db.execute(
            "select full_name, birthdate, classe, submitted_at from kyi where user_id = ?",
            (user["id"],),
        ).fetchone()
        photos = db.execute(
            "select id, created_at from photos where user_id = ?", (user["id"],)
        ).fetchall()
    return {
        "account": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "created_at": user["created_at"],
        },
        "profile": dict(profile) if profile else None,
        "kyi": dict(kyi) if kyi else None,
        "photos": [dict(photo) for photo in photos],
    }


@app.post("/api/account/delete")
def delete_account(payload: DeleteAccountPayload, user=Depends(current_user)):
    if not verify_password(payload.password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=403, detail="Mot de passe incorrect.")
    with get_db() as db:
        db.execute("delete from users where id = ?", (user["id"],))
    for folder in (KYI_DIR, UPLOADS_DIR):
        for path in folder.glob(f"{user['id']}-*") if folder.exists() else []:
            path.unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/push/key")
def push_key():
    return {"public_key": os.getenv("BC_VAPID_PUBLIC_KEY", "")}


@app.post("/api/push/subscribe")
def push_subscribe(subscription: PushSubscription, user=Depends(current_user)):
    with get_db() as db:
        db.execute(
            """
            insert into push_subs(endpoint, user_id, subscription_json)
            values (?, ?, ?)
            on conflict(endpoint) do update set
                user_id = excluded.user_id,
                subscription_json = excluded.subscription_json
            """,
            (subscription.endpoint, user["id"], subscription.model_dump_json()),
        )
    return {"ok": True}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(subscription: PushSubscription, user=Depends(current_user)):
    with get_db() as db:
        db.execute(
            "delete from push_subs where endpoint = ? and user_id = ?",
            (subscription.endpoint, user["id"]),
        )
    return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    with get_db() as db:
        user = db.execute(
            """
            select u.* from users u
            join sessions s on s.user_id = u.id
            where s.token = ?
            """,
            (token,),
        ).fetchone()
    if user is None or user["banned"]:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    active_sockets.setdefault(user["id"], set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_sockets.get(user["id"], set()).discard(websocket)


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


@app.get("/api/admin/kyi-card/{user_id}")
def get_kyi_card(user_id: int, user=Depends(current_admin)):
    from fastapi.responses import FileResponse

    with get_db() as db:
        row = db.execute("select card_path from kyi where user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Carte KYI introuvable.")
    path = KYI_DIR / row["card_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier KYI introuvable.")
    return FileResponse(path)


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
