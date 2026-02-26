from datetime import datetime, date
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from models import AttendanceRecord, User
from auth import hash_password


def get_today_record(db: Session, user_id: int) -> Optional[AttendanceRecord]:
    today = date.today().strftime("%Y-%m-%d")
    return (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.user_id == user_id, AttendanceRecord.date == today)
        .first()
    )


def punch(db: Session, user_id: int) -> Tuple[str, AttendanceRecord]:
    """出退勤トグル。
    1. レコードなし → 出勤打刻
    2. check_out なし → 退勤打刻
    3. check_out あり → 退勤取消（再打刻可能）
    """
    today = date.today().strftime("%Y-%m-%d")
    record = get_today_record(db, user_id)
    now = datetime.now().replace(microsecond=0)

    if record is None:
        record = AttendanceRecord(
            user_id=user_id,
            date=today,
            check_in=now,
            check_out=None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return "check_in", record

    if record.check_out is None:
        record.check_out = now
        db.commit()
        db.refresh(record)
        return "check_out", record

    # 退勤取消 → 退勤時刻をクリアして再打刻可能にする
    record.check_out = None
    db.commit()
    db.refresh(record)
    return "undo_check_out", record


def get_monthly_records(
    db: Session, user_id: int, year: int, month: int
) -> List[AttendanceRecord]:
    prefix = f"{year:04d}-{month:02d}"
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == user_id,
            AttendanceRecord.date.like(f"{prefix}-%"),
        )
        .order_by(AttendanceRecord.date)
        .all()
    )


def compute_work_minutes(record: AttendanceRecord) -> Optional[int]:
    if record.check_in and record.check_out:
        return int((record.check_out - record.check_in).total_seconds() / 60)
    return None


def get_all_users(db: Session) -> List[User]:
    return db.query(User).order_by(User.id).all()


def create_user(
    db: Session,
    username: str,
    password: str,
    display_name: str,
    is_admin: bool = False,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def toggle_user_active(db: Session, user_id: int) -> Optional[User]:
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_active = not user.is_active
        db.commit()
        db.refresh(user)
    return user
