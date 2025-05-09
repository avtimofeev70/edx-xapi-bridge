FROM python:3.11

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements/base.txt
RUN pip install --no-cache-dir -r requirements/production.txt

CMD ["sh", "-c", "python xapi_bridge $log_path"]
