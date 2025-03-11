FROM python:3.10-slim

WORKDIR /app

# Copy dependencies first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Port for Flask
EXPOSE 5000

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Start the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]