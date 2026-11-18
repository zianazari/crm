FROM python:3.13-slim
RUN pip install --no-cache-dir "fastapi==0.115.*" "uvicorn==0.34.*" "httpx==0.28.*"
WORKDIR /app
COPY app.py .
USER nobody
EXPOSE 8030
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8030"]
