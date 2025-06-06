# Dockerfile (Simpler Version for Current Goal)

# 1. Start FROM the official Airflow image you use in docker-compose.yaml
#    !! REPLACE with your actual base image and tag from docker-compose.yaml !!
FROM apache/airflow:2.8.1

# 2. OPTIONAL: If you need to install system packages (unlikely for these Python libs)
# USER root
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     #  build-essential \ # Only if a pip package needs compilation from C source
#      #  other-system-package \
#   && apt-get clean && rm -rf /var/lib/apt/lists/*

# 3. Switch to the airflow user (standard in official images)
USER airflow

# 4. Copy your project-specific Python requirements file into the image.
#    (Create 'requirements-airflow.txt' in the same directory as this Dockerfile)
COPY --chown=airflow:airflow requirements-airflow.txt /opt/airflow/requirements-airflow.txt

# 5. Install the Python dependencies using pip.
#    '--user' installs packages into the user's site-packages for the 'airflow' user.
RUN pip install --no-cache-dir --user -r /opt/airflow/requirements-airflow.txt