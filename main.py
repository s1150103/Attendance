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

# DB初期化
Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "change-me-in-production-please"),
)
templates = Jinja2Templates(directory="templates")


def _require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise _redirect_to_login()
    return user


def _redirect_to_login():
    return RedirectResponse("/login", status_code=302)


# 初期管理者アカウント作成
def _create_initial_admin():
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            crud.create_user(db, "admin", "admin", "管理者", is_admin=True)
    finally:
        db.close()


_create_initial_admin()


# ─────────────────────────────────────────
# ルート
# ─────────────────────────────────────────

@app.get("/")
def root(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login")
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "ユーザー名またはパスワードが正しくありません"},
        )
    login_user(request, user)
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=302)


@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return _redirect_to_login()
    record = crud.get_today_record(db, user.id)
    today = date.today()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "record": record,
            "today": today.strftime("%Y年%m月%d日"),
            "year": today.year,
            "month": today.month,
        },
    )


@app.post("/punch")
def punch(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return _redirect_to_login()
    crud.punch(db, user.id)
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/report")
def report(
    request: Request,
    db: Session = Depends(get_db),
    year: int = None,
    month: int = None,
):
    user = get_current_user(request, db)
    if not user:
        return _redirect_to_login()

    today = date.today()
    year = year or today.year
    month = month or today.month

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
            "prev_year": year if month > 1 else year - 1,
            "prev_month": month - 1 if month > 1 else 12,
            "next_year": year if month < 12 else year + 1,
            "next_month": month + 1 if month < 12 else 1,
        },
    )


@app.get("/export/csv")
def export_csv(
    request: Request,
    db: Session = Depends(get_db),
    year: int = None,
    month: int = None,
):
    user = get_current_user(request, db)
    if not user:
        return _redirect_to_login()

    today = date.today()
    year = year or today.year
    month = month or today.month

    records = crud.get_monthly_records(db, user.id, year, month)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["日付", "出勤時刻", "退勤時刻", "勤務時間(分)", "備考"])
    for r in records:
        mins = crud.compute_work_minutes(r)
        writer.writerow([
            r.date,
            r.check_in.strftime("%H:%M:%S") if r.check_in else "",
            r.check_out.strftime("%H:%M:%S") if r.check_out else "",
            mins if mins is not None else "",
            r.note or "",
        ])

    # BOM付きUTF-8 (Excel対応)
    content = "\ufeff" + output.getvalue()
    filename = f"attendance_{user.username}_{year}{month:02d}.csv"

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/admin/users")
def admin_users(request: Request, db: Session = Depends(get_db)):
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
    is_admin: str = Form(default=""),
):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse("/dashboard", status_code=302)

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

    crud.create_user(db, username, password, display_name, is_admin=bool(is_admin))
    return RedirectResponse("/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/toggle")
def admin_toggle_user(
    user_id: int, request: Request, db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return RedirectResponse("/dashboard", status_code=302)
    crud.toggle_user_active(db, user_id)
    return RedirectResponse("/admin/users", status_code=302)
