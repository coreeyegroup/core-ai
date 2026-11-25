FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
COPY requirements.txt /tmp/core-ai-doc-requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: -r /tmp/core-ai-doc-requirements.txt && python -m pip check
USER 65534:65534
