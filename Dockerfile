# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    binutils \
    && rm -rf /var/lib/apt/lists/*
# Install dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy project
COPY . .

# Collect static files (dummy SECRET_KEY only used at build time, not in production)
RUN SECRET_KEY=build-placeholder DB_NAME=x DB_USER=x DB_PASSWORD=x DB_HOST=x \
    python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Start the Django app using gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn dormwatch.wsgi:application -w 4 --bind 0.0.0.0:8000"]

