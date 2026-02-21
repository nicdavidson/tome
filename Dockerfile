FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TOME_HOST=0.0.0.0
ENV TOME_PORT=8080
ENV TOME_DB=/data/tome.db

EXPOSE 8080

CMD ["python", "run.py"]
