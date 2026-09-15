FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Hugging Face model cache — persisted on a docker volume so the ~82MB
# tinyroberta download survives container restarts.
ENV HF_HOME=/hf_cache
ENV TRANSFORMERS_CACHE=/hf_cache
ENV QA_MODEL_CACHE_DIR=/hf_cache

WORKDIR /app

COPY requirements.txt .

# Install CPU-only torch to keep the image lean. The default torch wheel
# ships with CUDA (~2GB); the CPU wheel is ~200MB.
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

COPY . .

# Pre-download the model into the image so the first request isn't slow.
# If this fails (no network at build time), skip — startup will fetch on
# demand instead.
RUN python -c "from qa import load_qa_pipeline; load_qa_pipeline()" || echo "model pre-download skipped"

EXPOSE 8002

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
