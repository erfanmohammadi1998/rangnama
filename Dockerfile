FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    HF_HOME=/models \
    SEG_MODEL_ID=facebook/mask2former-swin-base-ade-semantic

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r backend/requirements.txt

# مدل را داخل ایمیج دانلود می‌کنیم تا روی سرورِ بدون اینترنت هم بالا بیاید
RUN python -c "from transformers import AutoImageProcessor, Mask2FormerForUniversalSegmentation as M; m='facebook/mask2former-swin-base-ade-semantic'; AutoImageProcessor.from_pretrained(m); M.from_pretrained(m); print('model cached')"

COPY . .

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
