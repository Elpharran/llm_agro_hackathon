FROM python:3.10-slim

WORKDIR /code
COPY . /code/

COPY requirements.worker.txt /code/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH="${PYTHONPATH}:/code/bot"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git
    
RUN pip config set global.index-url https://pypi.org/simple

RUN pip install --no-cache-dir -r /code/requirements.worker.txt

EXPOSE 5672 15672
