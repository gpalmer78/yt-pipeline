FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8077
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8077/health', timeout=3).raise_for_status()"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8077"]
