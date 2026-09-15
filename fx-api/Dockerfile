FROM python:3.12-slim

ENV MALLOC_ARENA_MAX=2 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONUNBUFFERED=1
ENV PYTHONUNBUFFERED=1 PORT=8080
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "import pedalboard, numpy; print('pedalboard', pedalboard.__version__, 'numpy', numpy.__version__)"
COPY api ./api
EXPOSE 8080
CMD ["python", "api/fx.py"]
