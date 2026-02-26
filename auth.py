# =============================================================================
# auth.py - 認証ヘルパー
# =============================================================================
# パスワードのハッシュ化・検証と、セッション管理の関数をまとめたファイル。
#
# 【セッション認証の仕組み】
# 1. ログイン成功 → セッションにユーザーIDを保存
# 2. 次のリクエスト → セッションからIDを取り出してDBでユーザーを検索
# 3. ログアウト → セッションをクリア
# =============================================================================

from typing import Optional

import bcrypt
from fastapi import Request
from sqlalchemy.orm import Session

from models import User


def hash_password(password: str) -> str:
    """
    平文パスワードを bcrypt でハッシュ化して返す。

    bcrypt は同じパスワードでも毎回異なるハッシュを生成する（ソルト付き）ため、
    ハッシュが漏洩しても元のパスワードが特定されにくい。
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """
    入力された平文パスワードが、保存済みハッシュと一致するか検証する。

    bcrypt.checkpw が内部でソルトを考慮して比較してくれる。
    一致すれば True、不一致なら False を返す。
    """
    return bcrypt.checkpw(password.encode(), hashed.encode())


def get_current_user(request: Request, db: Session) -> Optional[User]:
    """
    セッションからログイン中のユーザーを取得する。

    セッションに user_id が保存されていなければ None を返す（未ログイン）。
    DBに存在しないIDや、無効化されたユーザーも None として扱う。

    各ルートでログインチェックに使う。
    例: user = get_current_user(request, db)
        if not user: return RedirectResponse("/login")
    """
    user_id = request.session.get("user_id")  # セッションからIDを取り出す
    if not user_id:
        return None  # 未ログイン
    # DBからユーザーを検索（is_active=True のもののみ）
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def login_user(request: Request, user: User):
    """
    ログイン成功時にセッションへユーザーIDを保存する。

    セッションは itsdangerous で署名されたCookieに保存されるため、
    クライアント側で改ざんしても検証で弾かれる。
    """
    request.session["user_id"] = user.id


def logout_user(request: Request):
    """
    セッションを全てクリアしてログアウトする。
    """
    request.session.clear()
