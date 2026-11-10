import base64
import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request, status

from .db import get_db

ITERATIONS = 200_000


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), actual_salt, ITERATIONS
    )
    return (
        base64.urlsafe_b64encode(digest).decode("ascii"),
        base64.urlsafe_b64encode(actual_salt).decode("ascii"),
    )


def verify_password(password: str, encoded_hash: str, encoded_salt: str) -> bool:
    salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, encoded_hash)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_db() as db:
        db.execute("insert into sessions(token, user_id) values (?, ?)", (token, user_id))
    return token


def _token_from_request(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification requise.")
    return token


def current_user(request: Request):
    token = _token_from_request(request)
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalide.")
    return user


def approved_user(user=Depends(current_user)):
    if not user["approved"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte en attente de validation.")
    return user


def current_admin(user=Depends(current_user)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Accès administrateur requis.")
    return user
