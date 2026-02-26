# =============================================================================
# crud.py - データベース操作（CRUD）
# =============================================================================
# CRUD = Create（作成）/ Read（読取）/ Update（更新）/ Delete（削除）
#
# ルート（main.py）から直接SQLを書かず、この関数群を呼び出すことで
# DB操作のロジックを一箇所にまとめている。
# =============================================================================

from datetime import datetime, date
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from models import AttendanceRecord, User
from auth import hash_password


def get_today_record(db: Session, user_id: int) -> Optional[AttendanceRecord]:
    """
    指定ユーザーの本日の出勤レコードを1件取得する。

    レコードがなければ None を返す（まだ出勤打刻していない状態）。
    """
    today = date.today().strftime("%Y-%m-%d")  # 例: "2024-10-21"
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == user_id,
            AttendanceRecord.date == today,
        )
        .first()
    )


def punch(db: Session, user_id: int) -> Tuple[str, AttendanceRecord]:
    """
    出退勤トグル処理。ボタンを押すたびに状態が切り替わる。

    状態の遷移:
      1. レコードなし         → 出勤打刻（check_in に現在時刻を記録）
      2. check_out が None    → 退勤打刻（check_out に現在時刻を記録）
      3. check_out が設定済み → 退勤取消（check_out を None に戻す）

    戻り値: (状態文字列, 更新後のレコード)
      - "check_in"        : 出勤打刻した
      - "check_out"       : 退勤打刻した
      - "undo_check_out"  : 退勤を取消した
    """
    today = date.today().strftime("%Y-%m-%d")
    record = get_today_record(db, user_id)
    now = datetime.now().replace(microsecond=0)  # マイクロ秒を切り捨てて見やすくする

    # ── 状態1: 本日のレコードがない → 出勤打刻 ──────────────────────────
    if record is None:
        record = AttendanceRecord(
            user_id=user_id,
            date=today,
            check_in=now,
            check_out=None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)  # DBが自動生成したidなどを反映させる
        return "check_in", record

    # ── 状態2: 出勤済みで退勤未打刻 → 退勤打刻 ──────────────────────────
    if record.check_out is None:
        record.check_out = now
        db.commit()
        db.refresh(record)
        return "check_out", record

    # ── 状態3: 退勤済み → 退勤取消（再打刻できるようにする） ─────────────
    record.check_out = None
    db.commit()
    db.refresh(record)
    return "undo_check_out", record


def get_monthly_records(
    db: Session, user_id: int, year: int, month: int
) -> List[AttendanceRecord]:
    """
    指定ユーザーの指定年月の出勤レコード一覧を日付順で返す。

    date カラムが "YYYY-MM-DD" の文字列のため、
    LIKE "YYYY-MM-%" で前方一致検索するだけで月次絞り込みができる。
    例: year=2024, month=10 → date LIKE "2024-10-%"
    """
    prefix = f"{year:04d}-{month:02d}"  # 例: "2024-10"
    return (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.user_id == user_id,
            AttendanceRecord.date.like(f"{prefix}-%"),  # LIKE "2024-10-%"
        )
        .order_by(AttendanceRecord.date)
        .all()
    )


def compute_work_minutes(record: AttendanceRecord) -> Optional[int]:
    """
    1件の出勤レコードから勤務時間（分）を計算して返す。

    check_in・check_out 両方が記録されていない場合は None を返す。
    ※休憩時間は考慮していない（出退勤時刻の差分をそのまま返す）
    """
    if record.check_in and record.check_out:
        delta = record.check_out - record.check_in  # timedelta
        return int(delta.total_seconds() / 60)       # 秒 → 分に変換
    return None


def get_all_users(db: Session) -> List[User]:
    """
    全ユーザー一覧をID順で返す（管理者画面用）。
    """
    return db.query(User).order_by(User.id).all()


def create_user(
    db: Session,
    username: str,
    password: str,
    display_name: str,
    is_admin: bool = False,
) -> User:
    """
    新しいユーザーを作成してDBに保存する。

    パスワードは平文のまま保存せず、hash_password() でハッシュ化してから保存する。
    """
    user = User(
        username=username,
        password_hash=hash_password(password),  # 必ずハッシュ化してから保存
        display_name=display_name,
        is_admin=is_admin,
        is_active=True,  # 作成直後は有効状態
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def toggle_user_active(db: Session, user_id: int) -> Optional[User]:
    """
    ユーザーの有効/無効を切り替える（管理者画面用）。

    is_active を True ↔ False で反転させる。
    無効化されたユーザーはログインできなくなる。
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_active = not user.is_active  # True → False / False → True
        db.commit()
        db.refresh(user)
    return user
