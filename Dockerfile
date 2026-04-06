FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./
COPY index.html ./
COPY login.html ./
COPY register.html ./
COPY styles.css ./
COPY app.js ./
COPY login.js ./
COPY register.js ./

ENV HOST=0.0.0.0
ENV PORT=4173
ENV DATA_DIR=/data

RUN mkdir -p /data

EXPOSE 4173

CMD ["python3", "server.py"]
