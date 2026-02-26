# ベースイメージ: 軽量なPython 3.11
FROM python:3.11-slim

# 作業ディレクトリ
WORKDIR /app

# 依存パッケージを先にインストール（キャッシュ効率化のため）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリコードをコピー
COPY . .

# ポート8000を公開
EXPOSE 8000

# 起動コマンド
# --host 0.0.0.0 : コンテナ外からのアクセスを許可
# DB_PATH は fly.toml の環境変数で /data/attendance.db に向ける
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
