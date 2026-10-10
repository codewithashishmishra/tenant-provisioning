FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir ".[dev]"

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
