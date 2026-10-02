FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

ARG APP_REV=2026-10-02-r2
RUN echo "T3R0ZA build: $APP_REV"

COPY . .
RUN python -m py_compile bot.py

EXPOSE 10000
CMD ["python", "bot.py"]
