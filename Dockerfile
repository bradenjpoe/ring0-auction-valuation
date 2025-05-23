FROM python:3.10-slim

# Install basic dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy your repo code
COPY . /app
WORKDIR /app

# Expose the port Render uses
EXPOSE 10000

# Run voila
CMD ["voila", "notebooks/hosted_v1.ipynb", "--port=10000", "--no-browser", "--strip_sources=True", "--Voila.ip=0.0.0.0", "--debug"]
