# =============================================================================
# database.py - データベース接続設定
# =============================================================================
# SQLAlchemyを使ってSQLite（ローカルファイルDB）に接続する設定ファイル。
# アプリ全体でこのファイルのセッションを使ってDBを操作する。
# =============================================================================

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLiteのファイルパス。
# ローカル: ./attendance.db（カレントディレクトリ）
# Fly.io : /data/attendance.db（永続ボリューム）
# 環境変数 DATABASE_URL が設定されていればそちらを優先する。
import os
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./attendance.db")

# DBエンジンの作成。
# check_same_thread=False は SQLite をマルチスレッド環境（FastAPI）で使うための設定。
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# DBセッションのファクトリ。
# autocommit=False: 明示的にcommit()を呼ぶまでDBに反映しない（安全のため）
# autoflush=False:  commit前に自動でSQLを発行しない
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORMモデル（models.py）の基底クラス。全テーブル定義はこれを継承する。
Base = declarative_base()


def get_db():
    """
    FastAPIのDependency Injection用のDB接続関数。

    ルート関数の引数に `db: Session = Depends(get_db)` と書くと
    FastAPIが自動でこの関数を呼び出し、DBセッションを渡してくれる。
    処理が終わったら finally で必ずセッションをクローズする。
    """
    db = SessionLocal()
    try:
        yield db        # ルート関数にセッションを渡す
    finally:
        db.close()      # 処理完了後（エラー時も含む）に必ずクローズ
