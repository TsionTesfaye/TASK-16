#!/bin/sh
set -e

# ── Auto-provision self-signed TLS certificates ──────────────
CERT="${TLS_CERT_PATH:-}"
KEY="${TLS_KEY_PATH:-}"

if [ -n "$CERT" ] && [ -n "$KEY" ]; then
    if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
        echo "[entrypoint] TLS cert/key not found — generating self-signed certificate..."
        mkdir -p "$(dirname "$CERT")" "$(dirname "$KEY")"
        openssl req -x509 -newkey rsa:2048 -nodes \
            -keyout "$KEY" \
            -out "$CERT" \
            -days 365 \
            -subj "/CN=localhost/O=ReclaimOps" \
            2>/dev/null
        chmod 600 "$KEY"
        echo "[entrypoint] Self-signed cert generated at $CERT (valid 365 days)"
    else
        echo "[entrypoint] TLS cert found at $CERT"
    fi
fi

# ── Launch Gunicorn with TLS if certs are configured ─────────
# When TLS_CERT_PATH and TLS_KEY_PATH point to readable files,
# override the default CMD to bind HTTPS on port 5443 with real
# TLS termination via Gunicorn's --certfile/--keyfile.
# Otherwise, fall through to whatever CMD was passed (plain HTTP).
if [ -n "$CERT" ] && [ -n "$KEY" ] && [ -f "$CERT" ] && [ -f "$KEY" ]; then
    echo "[entrypoint] Starting Gunicorn with TLS on :5443"
    exec gunicorn \
        --bind 0.0.0.0:5443 \
        --certfile="$CERT" \
        --keyfile="$KEY" \
        --workers 1 \
        --threads 2 \
        "app:create_app()"
fi

# No TLS configured — run the original CMD (plain HTTP dev mode)
exec "$@"
