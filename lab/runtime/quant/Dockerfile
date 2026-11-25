FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY requirements.txt /tmp/core-ai-quant-requirements.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: -r /tmp/core-ai-quant-requirements.txt && python -m pip check
USER 65534:65534
