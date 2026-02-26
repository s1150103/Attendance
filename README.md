# 出勤簿システム

ローカル環境で動作するシンプルな出勤簿Webアプリ。全て無料OSS。
複数ユーザー対応、出退勤打刻・月次レポート・CSVエクスポート機能付き。

---

## アーキテクチャ

| 要素 | 技術 | 理由 |
|------|------|------|
| Web フレームワーク | FastAPI | 軽量、型安全、async対応 |
| DB | SQLite + SQLAlchemy | インストール不要、ファイル1つ |
| テンプレート | Jinja2 | FastAPI標準 |
| CSS | Bootstrap 5 (CDN) | インストール不要 |
| 認証 | SessionMiddleware (itsdangerous) | JWTより簡単、ローカル向き |

---

## プロジェクト構成

```
attendance/
├── main.py                # FastAPIアプリ、全ルート
├── database.py            # SQLAlchemy エンジン・セッション
├── models.py              # ORMモデル: User, AttendanceRecord
├── auth.py                # パスワードハッシュ、セッションヘルパー
├── crud.py                # DBクエリ (punch, monthly records, etc.)
├── templates/
│   ├── base.html          # Bootstrapレイアウト、ナビゲーション
│   ├── login.html         # ログインフォーム
│   ├── dashboard.html     # 打刻ボタン（3状態）
│   ├── report.html        # 月次テーブル + CSVリンク
│   └── admin.html         # ユーザー管理（管理者のみ）
├── attendance.db          # 自動生成（gitignore済み）
└── requirements.txt
```

---

## DBスキーマ

### users

| カラム | 型 | 備考 |
|--------|-----|------|
| id | Integer PK | |
| username | String(50) unique | ログインID |
| password_hash | String(128) | bcrypt |
| display_name | String(100) | 表示名 |
| is_admin | Boolean | 管理者フラグ |
| is_active | Boolean | 有効フラグ |

### attendance_records

| カラム | 型 | 備考 |
|--------|-----|------|
| id | Integer PK | |
| user_id | FK → users.id | |
| date | String(10) | "YYYY-MM-DD"（1日1行） |
| check_in | DateTime | 出勤時刻 |
| check_out | DateTime | 退勤時刻 |
| note | String(200) | 備考 |

> **設計方針**: dateを文字列で保存 → `LIKE 'YYYY-MM-%'` で月次クエリが簡単。タイムゾーン問題なし。

---

## ルート一覧

| メソッド | パス | 認証 | 説明 |
|----------|------|------|------|
| GET | `/` | - | `/dashboard` or `/login` にリダイレクト |
| GET | `/login` | No | ログイン画面 |
| POST | `/login` | No | 認証 → セッション設定 |
| POST | `/logout` | Yes | セッションクリア |
| GET | `/dashboard` | Yes | 打刻ボタン + 本日状況 |
| POST | `/punch` | Yes | 出勤/退勤トグル |
| GET | `/report` | Yes | 月次レポート（`?year=&month=`） |
| GET | `/export/csv` | Yes | CSVダウンロード（`?year=&month=`） |
| GET | `/admin/users` | Admin | ユーザー一覧 |
| POST | `/admin/users/create` | Admin | ユーザー作成 |
| POST | `/admin/users/{id}/toggle` | Admin | ユーザー有効/無効切替 |

---

## セットアップ・起動

```bash
git clone https://github.com/aquacrew2/attendance.git
cd attendance
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

ブラウザで http://127.0.0.1 :8000 を開く。

### 初期ログイン

| ユーザー名 | パスワード | 権限 |
|-----------|-----------|------|
| `admin` | `admin` | 管理者 |

> 初回ログイン後、管理者画面からパスワード変更・ユーザー追加を推奨。

---

## セキュリティ

- パスワードは **bcrypt** でハッシュ化
- セッションは **itsdangerous** で署名
- SQLAlchemy ORM により **SQLインジェクション防止**
- 本番運用時は環境変数 `SESSION_SECRET` を必ず設定すること

```bash
export SESSION_SECRET="ランダムな長い文字列"
```

---

## CSVエクスポート

- エンコード: `utf-8-sig`（BOM付き）→ Excelで文字化けしない
- 出力項目: 日付・出勤時刻・退勤時刻・勤務時間(分)・備考

---

## 無料運用方法

| 方法 | 特徴 |
|------|------|
| **LAN運用**（推奨） | 同一ネットワーク内で共有。設定不要、データが手元に残る |
| **Oracle Cloud Always Free** | 24時間稼働、外部アクセス可能。VM2台が永久無料 |
| **Fly.io** | 永続ボリューム対応、コード変更最小でクラウド運用可能 |
