# Ground Truth runtime image, version runtime-1.0 (2026-11-15).
# The image holds only Python and the supervisor. The app code is bind-mounted read-only at /app
# and hot-reloads when /app/VERSION changes, so code updates never need an image rebuild.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC \
    GT_HOST=0.0.0.0 \
    GT_PORT=8790 \
    GT_APP=/app \
    GT_DATA=/data \
    GT_SEED=/seed

COPY supervise.py /opt/gt/supervise.py

# Unprivileged user. /data is created here so a new named volume inherits its ownership.
RUN useradd --system --uid 10001 --home /data gt \
 && mkdir -p /data \
 && chown gt:gt /data

USER gt
EXPOSE 8790
CMD ["python", "/opt/gt/supervise.py"]
