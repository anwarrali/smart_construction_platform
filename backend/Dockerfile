FROM python:3.11

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Apply committed schema changes before accepting traffic. Render and Railway
# supply PORT; local Docker keeps the existing 8000 default.
CMD ["sh", "-c", "alembic upgrade head && python -m app.db.bootstrap_admin --if-configured && python -m app.db.seed_demo --if-enabled && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers"]
