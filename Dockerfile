FROM python:slim-bookworm@sha256:c8137f4c460908c8763f281c8f22c431eb5c538514ba9553fc3a89c06b7cfb88

COPY requirements.txt .
RUN pip3 install -r requirements.txt

RUN apt-get update && apt-get install -y \
    default-mysql-client \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/
CMD ["python", "-u", "src/script.py"]
