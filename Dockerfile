FROM python:3.6

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 80
ENV PORT=80
ENV PYTHONPATH=/usr/src/app
CMD ["python", "app.py"]
