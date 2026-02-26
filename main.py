# =============================================================================
# main.py - FastAPI アプリケーション本体
# =============================================================================
# 全てのHTTPルート（URL）をここで定義する。
#
# 【リクエストの流れ】
#   ブラウザ → URL にアクセス → 対応するルート関数が実行 → HTMLを返す
#
# 【認証の仕組み】
#   ログイン済み → セッションに user_id が保存されている
#   未ログイン   → /login にリダイレクト
# =============================================================================

import csv
import io
import os
from datetime import date

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

import crud
from auth import get_current_user, login_user, logout_user, verify_password
from database import Base, SessionLocal, engine, get_db
from models import User

# =============================================================================
# アプリ初期化
# =============================================================================

# テーブルが存在しない場合に自動作成（models.py の定義を元にする）
Base.metadata.create_all(bind=engine)

app = FastAPI()

# セッションミドルウェアを追加。
# セッションデータはクライアントのCookieに保存され、SECRET_KEYで署名される。
# SECRET_KEYが漏洩するとセッションが偽造されるため、本番では環境変数で管理する。
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "change-me-in-production-please"),
)

# テンプレートエンジンの設定。templates/ フォルダの .html ファイルを使う。
templates = Jinja2Templates(directory="templates")


# =============================================================================
# ヘルパー関数
# =============================================================================

def _redirect_to_login():
    """未ログイン時のリダイレクト先。302 = 一時リダイレクト。"""
    return RedirectResponse("/login", status_code=302)


def _create_initial_admin():
    """
    DBが空（ユーザーが1人もいない）場合に、初期管理者アカウントを作成する。
    アプリ起動時に1度だけ実行される。
    初期パスワード admin は必ず変更すること。
    """
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            crud.create_user(db, "admin", "admin", "管理者", is_admin=True)
    finally:
        db.close()


# アプリ起動時に初期管理者を作成
_create_initial_admin()


# =============================================================================
# ルート定義
# =============================================================================

@app.get("/")
def root(request: Request, db: Session = Depends(get_db)):
    """
    トップページ。
    ログイン済みならダッシュボード、未ログインならログイン画面に振り分ける。
    """
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


# ─── ログイン / ログアウト ────────────────────────────────────────────────────

@app.get("/login")
def login_get(request: Request):
    """ログイン画面を表示する。"""
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),   # フォームの name="username" の値
    password: str = Form(...),   # フォームの name="password" の値
    db: Session = Depends(get_db),
):
    """
    ログインフォームの送信を処理する。

    1. ユーザー名でDBを検索（is_active=True のもののみ）
    2. パスワードをハッシュと照合
    3. 認証OK → セッションにIDを保存してダッシュボードへ
    4. 認証NG → エラーメッセージを表示
    """
    user = db.query(User).filter(
        User.username == username,
        User.is_active == True
    ).first()

    if not user or not verify_password(password, user.password_hash):
        # 認証失敗: ユーザーが存在しない OR パスワードが違う
        # セキュリティのため「どちらが間違いか」は教えない
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "ユーザー名またはパスワードが正しくありません"},
        )

    login_user(request, user)  # セッションに user_id を保存
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/logout")
def logout(request: Request):
    """セッションをクリアしてログイン画面に戻る。"""
    logout_user(request)
    return RedirectResponse("/login", status_code=302)


# ─── ダッシュボード（打刻） ──────────────────────────────────────────────────

@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """
    打刻画面。本日の出勤状態に応じてボタンの表示が変わる。

    ボタンの3状態:
      - 未打刻           → 「出勤する」ボタン
      - 出勤済み・退勤前 → 「退勤する」ボタン
      - 退勤済み         → 「退勤を取消す」ボタン
    """
    user = get_current_user(request, db)
    if not user:
        return _redirect_to_login()

    record = crud.get_today_record(db, user.id)  # 本日のレコードを取得
    today = date.today()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "record": record,           # None = 未打刻
            "today": today.strftime("%Y年%m月%d日"),
            "year": today.year,
            "month": today.month,
        },
    )


@app.post("/punch")
def punch(request: Request, db: Session = Depends(get_db)):
    """
    打刻ボタンが押されたときの処理。
    crud.punch() で出勤/退勤/取消を自動判定してDBを更新し、ダッシュボードに戻る。
    """
    user = get_current_user(request, db)
    if not user:
        return _redirect_to_login()

    crud.punch(db, user.id)
    return RedirectResponse("/dashboard", status_code=302)


# ─── 月次レポート ────────────────────────────────────────────────────────────

@app.get("/report")
def report(
    request: Request,
    db: Session = Depends(get_db),
    year: int = None,   # クエリパラメータ: ?year=2024
    month: int = None,  # クエリパラメータ: ?month=10
):
    """
    月次レポート画面。指定した年月の出勤一覧と合計勤務時間を表示する。
    year/month が省略された場合は今月を表示する。
    """
    user = get_current_user(request, db)
    if not user:
        return _redirect_to_login()

    today = date.today()
    year = year or today.year
    month = month or today.month

    # 指定月のレコードを取得して、勤務時間を計算
    records = crud.get_monthly_records(db, user.id, year, month)
    rows = []
    total_minutes = 0
    for r in records:
        mins = crud.compute_work_minutes(r)
        if mins:
            total_minutes += mins
        rows.append({"record": r, "work_minutes": mins})

    return templates.TemplateResponse(
        "report.html",
        {
            "request": request,
            "user": user,
            "rows": rows,
            "year": year,
            "month": month,
            "total_minutes": total_minutes,
            # 前月・次月ナビゲーション用（月をまたぐ場合は年も変える）
            "prev_year":  year if month > 1 else year - 1,
            "prev_month": month - 1 if month > 1 else 12,
            "next_year":  year if month < 12 else year + 1,
            "next_month": month + 1 if month < 12 else 1,
        },
    )


# ─── CSV エクスポート ────────────────────────────────────────────────────────

@app.get("/export/csv")
def export_csv(
    request: Request,
    db: Session = Depends(get_db),
    year: int = None,
    month: int = None,
):
    """
    指定月の出勤データを CSV ファイルとしてダウンロードさせる。

    StreamingResponse を使うことでメモリ効率よくファイルを返せる。
    BOM付きUTF-8（utf-8-sig）にすることで Excel で開いても文字化けしない。
    """
    user = get_current_user(request, db)
    if not user:
        return _redirect_to_login()

    today = date.today()
    year = year or today.year
    month = month or today.month

    records = crud.get_monthly_records(db, user.id, year, month)

    # CSV をメモリ上に生成する
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["日付", "出勤時刻", "退勤時刻", "勤務時間(分)", "備考"])
    for r in records:
        mins = crud.compute_work_minutes(r)
        writer.writerow([
            r.date,
            r.check_in.strftime("%H:%M:%S")  if r.check_in  else "",
            r.check_out.strftime("%H:%M:%S") if r.check_out else "",
            mins if mins is not None else "",
            r.note or "",
        ])

    # BOM（\ufeff）を先頭に付けて Excel の文字化けを防ぐ
    content = "\ufeff" + output.getvalue()
    filename = f"attendance_{user.username}_{year}{month:02d}.csv"

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── 管理者：ユーザー管理 ───────────────────────────────────────────────────

@app.get("/admin/users")
def admin_users(request: Request, db: Session = Depends(get_db)):
    """
    管理者専用のユーザー一覧画面。
    管理者でないユーザーがアクセスするとダッシュボードに戻す。
    """
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse("/dashboard", status_code=302)

    users = crud.get_all_users(db)
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "user": user, "users": users, "error": None},
    )


@app.post("/admin/users/create")
def admin_create_user(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    is_admin: str = Form(default=""),  # チェックボックスは値なしで送信されるためデフォルト=""
):
    """
    管理者画面からの新規ユーザー作成。
    同名のユーザーが既にいる場合はエラーを表示する。
    """
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse("/dashboard", status_code=302)

    # ユーザー名の重複チェック
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        users = crud.get_all_users(db)
        return templates.TemplateResponse(
            "admin.html",
            {
                "request": request,
                "user": user,
                "users": users,
                "error": f"ユーザー名 '{username}' は既に使用されています",
            },
        )

    # is_admin チェックボックスが送信された場合は "1" が来る、未選択は ""
    crud.create_user(db, username, password, display_name, is_admin=bool(is_admin))
    return RedirectResponse("/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/toggle")
def admin_toggle_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    ユーザーの有効/無効を切り替える。
    無効化されたユーザーはログインできなくなる（データは削除しない）。
    """
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse("/dashboard", status_code=302)

    crud.toggle_user_active(db, user_id)
    return RedirectResponse("/admin/users", status_code=302)
