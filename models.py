# =============================================================================
# models.py - データベーステーブル定義（ORM モデル）
# =============================================================================
# SQLAlchemy の ORM（Object-Relational Mapping）を使ってテーブルをクラスで定義する。
# クラス = テーブル、インスタンス = 1行のデータ、として扱える。
# =============================================================================

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base  # declarative_base() で作った基底クラス


class User(Base):
    """
    ユーザーテーブル（users）

    ログインアカウントの情報を管理する。
    管理者フラグ（is_admin）で一般ユーザーと管理者を区別する。
    """
    __tablename__ = "users"  # 実際のテーブル名

    id           = Column(Integer, primary_key=True, index=True)  # 自動採番の主キー
    username     = Column(String(50), unique=True, nullable=False) # ログインID（重複不可）
    password_hash = Column(String(128), nullable=False)            # bcryptハッシュ済みPW
    display_name = Column(String(100), nullable=False)             # 画面表示名
    is_admin     = Column(Boolean, default=False)                  # True=管理者
    is_active    = Column(Boolean, default=True)                   # False=無効（ログイン不可）

    # リレーション: このユーザーの出勤レコード一覧を records で参照できる
    # 例: user.records → [AttendanceRecord, ...]
    records = relationship("AttendanceRecord", back_populates="user")


class AttendanceRecord(Base):
    """
    出勤レコードテーブル（attendance_records）

    1ユーザー1日につき1行のデータを持つ。
    check_in（出勤時刻）と check_out（退勤時刻）を記録する。
    """
    __tablename__ = "attendance_records"

    id       = Column(Integer, primary_key=True, index=True)          # 自動採番の主キー
    user_id  = Column(Integer, ForeignKey("users.id"), nullable=False) # 外部キー → users.id
    date     = Column(String(10), nullable=False)  # "YYYY-MM-DD" 形式の文字列
                                                   # ※DateType でなく文字列にすることで
                                                   #   LIKE クエリで月次集計が簡単になる
    check_in  = Column(DateTime, nullable=True)    # 出勤時刻（打刻前はNone）
    check_out = Column(DateTime, nullable=True)    # 退勤時刻（退勤前はNone）
    note      = Column(String(200), default="")    # 備考（有給・夏休みなど）

    # リレーション: このレコードのユーザー情報を user で参照できる
    # 例: record.user.display_name → "佐藤 彰"
    user = relationship("User", back_populates="records")
