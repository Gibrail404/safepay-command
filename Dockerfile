# API image. Serving needs neither PyTorch nor LightGBM (those are for training and for the optional risk tool), which keeps it small.
# The OFAC list is downloaded at build time from the official source, so the image carries the list as of the build date.
FROM python:3.12-slim
ENV PIP_DEFAULT_TIMEOUT=100 PIP_RETRIES=6 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/kernel:/app/screening:/app/lab:/app/ml:/app/pipelines
WORKDIR /app
RUN pip install pandas numpy scipy pyarrow pyyaml fastapi "uvicorn[standard]" httpx pydantic sqlalchemy "psycopg[binary]" scikit-learn rapidfuzz spacy \
 && (for i in 1 2 3; do python -m spacy download en_core_web_sm && break || { echo "model download failed, retry $i"; sleep 3; }; done; python -c "import spacy; spacy.load('en_core_web_sm')")
COPY pipelines ./pipelines
COPY data/registry.yaml ./data/registry.yaml
RUN python -m safepay_data ofac_sdn ofac_alt
COPY kernel ./kernel
COPY screening ./screening
COPY lab ./lab
COPY config ./config
COPY docs/reports ./docs/reports
# Optional: the Interception page needs the risk model and a sample of real held-out transactions. `scripts/prepare_demo_assets.sh` fills deploy/demo_assets; without it the page answers 503.
COPY deploy/demo_assets/ /tmp/demo_assets/
RUN if [ -f /tmp/demo_assets/scenario_pool.parquet ]; then \
      apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* && pip install lightgbm \
      && mkdir -p /app/data/processed && cp /tmp/demo_assets/scenario_pool.parquet /app/data/processed/ && cp -R /tmp/demo_assets/models /app/models && cp -R /tmp/demo_assets/ml /app/ml; fi \
 && rm -rf /tmp/demo_assets
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
ENV PORT=7860
EXPOSE 7860
# Required at run time: DATABASE_URL, SAFEPAY_TENANTS ("tenant:key:role,..."), SAFEPAY_CAPABILITY_SECRET. Optional: OLLAMA_API_KEY, SAFEPAY_CORS_ORIGINS.
CMD ["sh", "-c", "uvicorn --factory safepay.api:create_app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS:-1}"]
