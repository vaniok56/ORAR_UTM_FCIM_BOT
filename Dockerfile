FROM python:3.13.3-slim-bookworm

COPY requirements.txt .
RUN pip3 install -r requirements.txt

RUN apt-get update && apt-get install -y \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "script.py"]