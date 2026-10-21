# AyahOS sandbox job image (Python only). Build from the repository root:
#   docker build -f deploy/sandbox/Dockerfile -t ayahos/sandbox-python:local .
# Deploy it by digest (AYAHOS_SANDBOX_IMAGE=...@sha256:...); the worker refuses tags.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

COPY deploy/sandbox/requirements.lock /tmp/requirements.lock
RUN set -eux; \
    if grep -qvE '^\s*(#|$)' /tmp/requirements.lock; then \
        pip install --no-cache-dir --no-deps --require-hashes -r /tmp/requirements.lock; \
    fi; \
    rm -f /tmp/requirements.lock; \
    pip uninstall --yes pip setuptools wheel || true; \
    rm -rf /root/.cache /usr/local/bin/pip* /usr/local/bin/idle* /usr/local/bin/pydoc*

COPY apps/sandbox_worker/sandbox_worker/runner.py /opt/ayahos/runner.py
RUN chmod 0755 /opt/ayahos && chmod 0444 /opt/ayahos/runner.py

USER 65534:65534
WORKDIR /tmp
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "-I", "-S", "/opt/ayahos/runner.py"]
