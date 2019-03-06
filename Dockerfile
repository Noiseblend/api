FROM python:3.7

VOLUME /cache

COPY requirements.txt /
RUN pip install -U pip
RUN pip install --cache-dir /cache -r /requirements.txt

COPY . /app

WORKDIR /app
RUN python setup.py install

CMD ["python", "-m", "noiseblend_api.api"]