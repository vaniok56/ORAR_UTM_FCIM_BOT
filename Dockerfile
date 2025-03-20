FROM python:3.9.16-slim-buster
COPY . .
RUN pip3 install -r requirements.txt
ENV PYTHONUNBUFFERED=1
CMD python -u script.py