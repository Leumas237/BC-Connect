import asyncio
import csv
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime
from io import StringIO
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, Response
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
from .db import get_db, initialize_database, today_condition
from .storage import delete_asset, download_asset, upload_asset

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
MAX_KYI_SIZE = 5 * 1024 * 1024
MAX_PHOTO_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
active_sockets: dict[int, set[WebSocket]] = {}
main_loop: asyncio.AbstractEventLoop | None = None

app = FastAPI(title=settings.app_name)


def csv_safe(value) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


async def notify_user(user_id: int, event: dict) -> None:
    sockets = list(active_sockets.get(user_id, set()))
    for socket in sockets:
        try:
            await socket.send_json(event)
        except (OSError, RuntimeError):
            active_sockets.get(user_id, set()).discard(socket)


def current_daily_likes(db, user_id: int) -> int:
    row = db.execute(
        f"""
        select count(*) as count from swipes
        where swiper_id = ? and liked = 1 and {today_condition("created_at")}
        """,
        (user_id,),
    ).fetchone()
    return int(row["count"])


def log_activity(
    db,
    actor_id: int | None,
    action: str,
    target_type: str = "",
    target_id: int | None = None,
    details: str = "",
) -> None:
    db.execute(
        """
        insert into activity_logs(actor_id, action, target_type, target_id, details)
        values (?, ?, ?, ?, ?)
        """,
        (actor_id, action, target_type, target_id, details),
    )


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
    moderator_code: str = Field(default="", max_length=120)


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


class WallReactionPayload(BaseModel):
    reaction: str = Field(default="like", pattern="^(like|love|support)$")


class WallCommentPayload(BaseModel):
    body: str = Field(min_length=1, max_length=500)


class ModeratorCodePayload(BaseModel):
    code: str = Field(min_length=8, max_length=120)


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
        if not is_admin and payload.moderator_code.strip():
            moderator_code = db.execute(
                "select code_hash, code_salt from moderator_codes where id = 1"
            ).fetchone()
            if moderator_code and verify_password(
                payload.moderator_code.strip(),
                moderator_code["code_hash"],
                moderator_code["code_salt"],
            ):
                is_admin = 1
        try:
            cursor = db.execute(
                """
                insert into users(
                    email, password_hash, password_salt, name, is_admin, approved, policy_accepted_at
                )
                values (?, ?, ?, ?, ?, ?, ?)
                returning id
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
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Cette adresse est déjà inscrite.") from exc
        user_id = cursor.fetchone()["id"]
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
    suffix = Path(photo.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    filename = f"{user['id']}-{secrets.token_hex(12)}{suffix}"
    storage_key = f"photos/{filename}"
    upload_asset(storage_key, content, photo.content_type)
    with get_db() as db:
        cursor = db.execute(
            "insert into photos(user_id, filename, content_type) values (?, ?, ?) returning id",
            (user["id"], storage_key, photo.content_type),
        )
    return {"id": cursor.fetchone()["id"]}


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
    delete_asset(photo["filename"])
    return {"ok": True}


@app.get("/api/profile/photo/{photo_id}")
def get_profile_photo(photo_id: int, user=Depends(approved_user)):
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
    try:
        content = download_asset(photo["filename"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Photo introuvable.") from None
    return Response(content=content, media_type=photo["content_type"])


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
    quota_message = ""
    quota_banned = False
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
                quota_banned = True
            quota_message = (
                "Compte suspendu pour dépassement répété du quota."
                if strikes >= settings.spam_strikes_ban
                else f"Quota quotidien atteint ({settings.daily_likes} likes)."
            )
        if not quota_message:
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
                        "insert into matches(user_a, user_b) values (?, ?) on conflict do nothing",
                        (user_a, user_b),
                    )
                    matched = True
    if quota_message:
        raise HTTPException(
            status_code=403 if quota_banned else 429,
            detail=quota_message,
        )
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
        log_activity(db, user["id"], "report_created", "user", payload.target_id, payload.reason.strip())
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
            log_activity(db, user["id"], "report_banned", "report", report_id, f"user_id={report_row['reported_id']}")
        else:
            db.execute("update reports set status = 'dismissed' where id = ?", (report_id,))
            log_activity(db, user["id"], "report_dismissed", "report", report_id)
    return {"ok": True, "status": "banned" if payload.action == "ban" else "dismissed"}


@app.get("/api/admin/stats")
def admin_stats(user=Depends(current_admin)):
    with get_db() as db:
        stats = db.execute(
            f"""
            select
                (select count(*) from users) as total_users,
                (select count(*) from users where approved = 1 and banned = 0) as approved_users,
                (select count(*) from users where approved = 0 and banned = 0) as pending_users,
                (select count(*) from users where banned = 1) as banned_users,
                (select count(*) from reports where status = 'pending') as pending_reports,
                (select count(*) from matches) as total_matches,
                (select count(*) from swipes where liked = 1 and {today_condition("created_at")}) as likes_today
            """
        ).fetchone()
    return dict(stats)


@app.post("/api/admin/moderator-code")
def set_moderator_code(payload: ModeratorCodePayload, user=Depends(current_admin)):
    code_hash, code_salt = hash_password(payload.code.strip())
    with get_db() as db:
        db.execute(
            """
            insert into moderator_codes(id, code_hash, code_salt, created_by)
            values (1, ?, ?, ?)
            on conflict(id) do update set
                code_hash = excluded.code_hash,
                code_salt = excluded.code_salt,
                created_by = excluded.created_by,
                created_at = current_timestamp
            """,
            (code_hash, code_salt, user["id"]),
        )
        log_activity(db, user["id"], "moderator_code_changed", "system")
    return {"ok": True}


@app.get("/api/admin/activity")
def admin_activity(user=Depends(current_admin)):
    with get_db() as db:
        rows = db.execute(
            """
            select a.id, a.action, a.target_type, a.target_id, a.details, a.created_at,
                   coalesce(u.email, 'Système') as actor_email
            from activity_logs a
            left join users u on u.id = a.actor_id
            order by a.created_at desc, a.id desc
            limit 200
            """
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/admin/activity.csv")
def export_admin_activity(user=Depends(current_admin)):
    with get_db() as db:
        rows = db.execute(
            """
            select a.id, a.created_at, coalesce(u.email, 'Système') as actor_email,
                   a.action, a.target_type, a.target_id, a.details
            from activity_logs a
            left join users u on u.id = a.actor_id
            order by a.created_at desc, a.id desc
            """
        ).fetchall()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "date", "acteur", "action", "type_cible", "id_cible", "details"])
    writer.writerows(
        (
            csv_safe(row["id"]),
            csv_safe(row["created_at"]),
            csv_safe(row["actor_email"]),
            csv_safe(row["action"]),
            csv_safe(row["target_type"]),
            csv_safe(row["target_id"] or ""),
            csv_safe(row["details"]),
        )
        for row in rows
    )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=bc-connect-activity.csv"},
    )


@app.get("/api/wall")
def wall(user=Depends(approved_user)):
    with get_db() as db:
        rows = db.execute(
            """
            select p.id, p.user_id, u.name, p.body, p.media_filename,
                   p.media_content_type, p.created_at,
                   (p.user_id = ?) as is_mine,
                   (select count(*) from wall_reactions r where r.post_id = p.id) as reactions,
                   (select count(*) from wall_comments c where c.post_id = p.id) as comments,
                   (select reaction from wall_reactions r where r.post_id = p.id and r.user_id = ?) as my_reaction
            from wall_posts p
            join users u on u.id = p.user_id
            where u.banned = 0
            order by p.created_at desc, p.id desc
            limit 100
            """,
            (user["id"], user["id"]),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/wall/posts", status_code=status.HTTP_201_CREATED)
async def create_wall_post(
    body: str = Form(default="", max_length=2000),
    media: UploadFile | None = File(default=None),
    user=Depends(approved_user),
):
    content = body.strip()
    media_bytes = b""
    filename = None
    content_type = None
    if media is not None:
        if media.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Le média doit être une image JPG, PNG ou WEBP.")
        media_bytes = await media.read(MAX_PHOTO_SIZE + 1)
        if len(media_bytes) > MAX_PHOTO_SIZE:
            raise HTTPException(status_code=413, detail="L’image ne doit pas dépasser 5 Mo.")
        suffix = Path(media.filename or "").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        filename = f"wall-{user['id']}-{secrets.token_hex(12)}{suffix}"
        content_type = media.content_type
    if not content and not media_bytes:
        raise HTTPException(status_code=400, detail="Ajoute un texte ou une image.")
    if media_bytes:
        filename = f"wall/{filename}"
        upload_asset(filename, media_bytes, content_type)
    with get_db() as db:
        cursor = db.execute(
            """
            insert into wall_posts(user_id, body, media_filename, media_content_type)
            values (?, ?, ?, ?) returning id
            """,
            (user["id"], content, filename, content_type),
        )
        post_id = cursor.fetchone()["id"]
        log_activity(db, user["id"], "wall_post_created", "post", post_id)
    return {"ok": True, "post_id": post_id}


@app.delete("/api/wall/posts/{post_id}")
def delete_wall_post(post_id: int, user=Depends(approved_user)):
    with get_db() as db:
        post = db.execute(
            "select user_id, media_filename from wall_posts where id = ?", (post_id,)
        ).fetchone()
        if post is None:
            raise HTTPException(status_code=404, detail="Publication introuvable.")
        if post["user_id"] != user["id"] and not user["is_admin"]:
            raise HTTPException(status_code=403, detail="Suppression non autorisée.")
        db.execute("delete from wall_posts where id = ?", (post_id,))
        log_activity(db, user["id"], "wall_post_deleted", "post", post_id)
    if post["media_filename"]:
        delete_asset(post["media_filename"])
    return {"ok": True}


@app.get("/api/wall/media/{filename}")
def wall_media(filename: str, user=Depends(approved_user)):
    with get_db() as db:
        exists = db.execute(
            "select 1 from wall_posts where media_filename = ?", (filename,)
        ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="Média introuvable.")
    try:
        content = download_asset(filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Média introuvable.") from None
    return Response(content=content)


@app.post("/api/wall/posts/{post_id}/reaction")
def react_to_wall_post(post_id: int, payload: WallReactionPayload, user=Depends(approved_user)):
    with get_db() as db:
        if db.execute("select 1 from wall_posts where id = ?", (post_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Publication introuvable.")
        db.execute(
            """
            insert into wall_reactions(post_id, user_id, reaction)
            values (?, ?, ?)
            on conflict(post_id, user_id) do update set reaction = excluded.reaction
            """,
            (post_id, user["id"], payload.reaction),
        )
    return {"ok": True}


@app.delete("/api/wall/posts/{post_id}/reaction")
def remove_wall_reaction(post_id: int, user=Depends(approved_user)):
    with get_db() as db:
        db.execute(
            "delete from wall_reactions where post_id = ? and user_id = ?",
            (post_id, user["id"]),
        )
    return {"ok": True}


@app.post("/api/wall/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
def comment_on_wall_post(post_id: int, payload: WallCommentPayload, user=Depends(approved_user)):
    with get_db() as db:
        if db.execute("select 1 from wall_posts where id = ?", (post_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Publication introuvable.")
        cursor = db.execute(
            "insert into wall_comments(post_id, user_id, body) values (?, ?, ?) returning id",
            (post_id, user["id"], payload.body.strip()),
        )
        log_activity(db, user["id"], "wall_comment_created", "post", post_id)
    return {"ok": True, "comment_id": cursor.fetchone()["id"]}


@app.get("/api/wall/posts/{post_id}/comments")
def wall_comments(post_id: int, user=Depends(approved_user)):
    with get_db() as db:
        rows = db.execute(
            """
            select c.id, c.body, c.created_at, u.name
            from wall_comments c join users u on u.id = c.user_id
            where c.post_id = ?
            order by c.created_at asc, c.id asc
            """,
            (post_id,),
        ).fetchall()
    return [dict(row) for row in rows]


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
        asset_rows = db.execute(
            """
            select filename as asset_key from photos where user_id = ?
            union all
            select card_path as asset_key from kyi where user_id = ?
            union all
            select media_filename as asset_key from wall_posts
            where user_id = ? and media_filename is not null
            """,
            (user["id"], user["id"], user["id"]),
        ).fetchall()
        db.execute("delete from users where id = ?", (user["id"],))
    for asset in asset_rows:
        delete_asset(asset["asset_key"])
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

    suffix = Path(card.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    filename = f"{user['id']}-{secrets.token_hex(12)}{suffix}"
    storage_key = f"kyi/{filename}"
    upload_asset(storage_key, content, card.content_type)

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
            (user["id"], full_name.strip(), birthdate.strip(), classe.strip(), storage_key),
        )
    if previous and previous["card_path"] != storage_key:
        delete_asset(previous["card_path"])
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
    with get_db() as db:
        row = db.execute("select card_path from kyi where user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Carte KYI introuvable.")
    try:
        content = download_asset(row["card_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Fichier KYI introuvable.") from None
    return Response(content=content, media_type="application/octet-stream")


@app.post("/api/admin/kyi/{user_id}/decision")
def decide_kyi(user_id: int, payload: KyiDecision, user=Depends(current_admin)):
    with get_db() as db:
        target = db.execute("select id from users where id = ?", (user_id,)).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
        card = db.execute("select card_path from kyi where user_id = ?", (user_id,)).fetchone()
        if payload.approved:
            db.execute("update users set approved = 1 where id = ?", (user_id,))
            log_activity(db, user["id"], "kyi_approved", "user", user_id)
        else:
            db.execute("delete from users where id = ?", (user_id,))
            log_activity(db, user["id"], "kyi_rejected", "user", user_id)
    if not payload.approved and card:
        delete_asset(card["card_path"])
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
