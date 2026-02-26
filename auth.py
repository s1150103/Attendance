from typing import Optional

import bcrypt
from fastapi import Request
from sqlalchemy.orm import Session

from models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def login_user(request: Request, user: User):
    request.session["user_id"] = user.id


def logout_user(request: Request):
    request.session.clear()
