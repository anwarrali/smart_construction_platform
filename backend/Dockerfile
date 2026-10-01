FROM python:3.11

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# The one start sequence, for every environment: Docker Compose, Railway and
# Render all run this CMD, and nothing overrides it (asserted by
# tests/test_start_sequence.py). In order:
#
#   1. wait for the database;
#   2. apply migrations — schema only;
#   3. initialize RBAC: create the configured initial administrator, or, when
#      none is configured, just seed the role templates on a fresh database;
#   4. the demo seed, only when explicitly enabled;
#   5. serve.
#
# The wait is not a delay — it polls and proceeds the instant the database
# answers. Without it, a database that is merely slow (still recovering, or
# briefly unreachable) makes Alembic fail, which kills the container, which a
# restart policy brings straight back into the same failure. Render and Railway
# supply PORT; local Docker keeps the existing 8000 default.
CMD ["sh", "-c", "python scripts/wait_for_db.py && alembic upgrade head && python -m app.db.bootstrap_admin --if-configured && python -m app.db.seed_demo --if-enabled && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers"]
