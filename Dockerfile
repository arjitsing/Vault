FROM python:3.10-slim

WORKDIR /app

COPY get_url/requirements.txt .
RUN pip install -r requirements.txt

COPY get_url/app.py .

EXPOSE 8080

CMD ["python", "app.py"]
