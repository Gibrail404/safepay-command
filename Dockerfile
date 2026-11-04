# API image. Serving needs neither PyTorch nor LightGBM (those are for training and for the optional risk tool), which keeps it small.
# The OFAC list is downloaded at build time from the official source, so the image carries the list as of the build date.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/kernel:/app/screening:/app/lab:/app/pipelines
WORKDIR /app
RUN pip install pandas numpy scipy pyarrow pyyaml fastapi "uvicorn[standard]" httpx pydantic sqlalchemy "psycopg[binary]" scikit-learn rapidfuzz spacy \
 && python -m spacy download en_core_web_sm
COPY pipelines ./pipelines
COPY data/registry.yaml ./data/registry.yaml
RUN python -m safepay_data ofac_sdn ofac_alt
COPY kernel ./kernel
COPY screening ./screening
COPY lab ./lab
COPY config ./config
COPY docs/reports ./docs/reports
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
ENV PORT=7860
EXPOSE 7860
# Required at run time: DATABASE_URL, SAFEPAY_TENANTS ("tenant:key:role,..."), SAFEPAY_CAPABILITY_SECRET. Optional: OLLAMA_API_KEY, SAFEPAY_CORS_ORIGINS.
CMD ["sh", "-c", "uvicorn --factory safepay.api:create_app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS:-1}"]
