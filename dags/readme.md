# Airbnb Data ETL Pipeline with Apache Airflow & AWS S3 ☁️

## Description

This project implements an automated ETL (Extract, Transform, Load) pipeline for Airbnb listing data, orchestrated by Apache Airflow running locally via Docker. The pipeline fetches data for a specified city (New York City), processes it using Python and Pandas, and loads the cleaned, transformed data in Parquet format into an Amazon S3 bucket.

This project demonstrates a more production-like approach to data pipelining, showcasing skills in:
*   **Workflow Orchestration:** Defining, scheduling, and monitoring a multi-step data pipeline using Apache Airflow.
*   **API Interaction & Data Ingestion:** Downloading data from an external source (Inside Airbnb).
*   **Data Processing & Transformation:** Cleaning, transforming, and structuring data efficiently using Pandas.
*   **Optimized File Formats:** Saving processed data as Apache Parquet for efficient storage and analytics.
*   **Cloud Storage Integration:** Programmatically interacting with Amazon S3 using Boto3 for storing raw and processed data.
*   **Docker & Docker Compose:** Running a complex application like Apache Airflow and its dependencies locally.
*   **Secure Configuration:** Managing sensitive credentials and parameters.
*   **Logging & Error Handling:** Implementing logging within Airflow tasks for traceability.

## Project Workflow 🌊

The pipeline is defined as an Apache Airflow DAG with the following key tasks:

1.  **Download & Decompress Data (`download_and_decompress_raw_data` task):**
    *   Fetches the `listings.csv.gz` file for the configured city/date from Inside Airbnb.
    *   Saves the raw gzipped file to a local staging area (within the Airflow worker environment).
    *   Decompresses the `.gz` file to a raw `.csv` file.
    *   Pushes the file paths of both the `.gz` and `.csv` files to Airflow XComs for downstream tasks.
2.  **Transform Data (`transform_airbnb_listings_data` task):**
    *   Pulls the raw CSV file path from XComs.
    *   Reads the CSV into a Pandas DataFrame.
    *   Performs data cleaning (e.g., price conversion, date parsing, handling missing values) and transformations (e.g., selecting relevant columns).
    *   Saves the transformed DataFrame as an Apache Parquet file in the local staging area.
    *   Pushes the file path of the processed Parquet file to XComs.
3.  **Upload Processed Data to S3 (`upload_processed_parquet_to_s3` task):**
    *   Pulls the processed Parquet file path from XComs.
    *   Uploads the Parquet file to a designated "processed" zone in an Amazon S3 bucket using Boto3.
    *   The S3 object key includes the DAG execution date for versioning/uniqueness.

### Airflow DAG Visualization

*(Embed a screenshot of your Airflow DAG's Graph View here. Make sure it shows the tasks and their dependencies clearly.)*

Example:
`![Airflow DAG Graph View](docs/images/airbnb_airflow_dag.png)`
*(Create this `docs/images` path in your repo or adjust as needed.)*

### Data Storage in S3

*(Optional: Embed a screenshot showing your processed Parquet file in your S3 bucket.)*

Example:
`![S3 Processed Data](docs/images/airbnb_s3_processed.png)`

## Tech Stack & Tools 🛠️

*   **Orchestration:** Apache Airflow
*   **Cloud Provider:** Amazon Web Services (AWS) ☁️
    *   **Storage:** Amazon S3
    *   **Identity:** AWS IAM (for user permissions used by Boto3)
*   **Language:** Python 3.x 🐍
*   **Key Python Libraries:**
    *   `apache-airflow` (and relevant providers if used, though likely core operators here)
    *   `requests` (for HTTP GET requests)
    *   `pandas` (for data manipulation)
    *   `pyarrow` (for Parquet file format support with Pandas)
    *   `boto3` (AWS SDK for Python)
    *   `python-dotenv` (for Airflow's local `.env` for `AIRFLOW_UID`)
    *   `logging` (Python's standard logging, utilized by Airflow tasks)
*   **Containerization:** Docker & Docker Compose (for running Airflow locally)
*   **Database (for Airflow Metadata):** PostgreSQL (managed by Airflow's Docker Compose)
*   **Version Control:** Git & GitHub

## Setup and Usage 🚀

### Prerequisites

*   Docker Desktop installed and running.
*   An AWS Account with an IAM user configured with:
    *   Programmatic access (Access Key ID & Secret Access Key).
    *   Permissions to interact with S3 (e.g., `AmazonS3FullAccess` or a more specific policy for your target bucket).
*   Local AWS credentials configured (typically in `~/.aws/credentials` and `~/.aws/config`) for Boto3 to use.
*   A target S3 bucket created for storing the processed Airbnb data.

### Project Setup (Local)

1.  **Clone the repository:**
    ```bash
    git clone [Your GitHub Repository URL for this project]
    cd [your-repo-name]
    ```
2.  **Prepare Airflow Environment (First Time Setup):**
    *   Download the official `docker-compose.yaml` for Apache Airflow into this project directory:
        ```bash
        # Replace with the latest stable version command from Airflow docs
        curl -LfO 'https://airflow.apache.org/docs/apache-airflow/STABLE_VERSION/docker-compose.yaml'
        ```
    *   Create necessary directories for Airflow (if not already present from cloning):
        ```bash
        mkdir -p ./dags ./logs ./plugins ./config ./dags/data_staging
        ```
    *   Set the `AIRFLOW_UID` for correct file permissions:
        ```bash
        echo -e "AIRFLOW_UID=$(id -u)" > .env
        ```
    *   Initialize the Airflow metadata database:
        ```bash
        docker-compose up airflow-init
        ```
3.  **Configure DAG:**
    *   Open `dags/airbnb_pipeline_dag.py`.
    *   **CRITICAL:** Update the `NYC_LISTINGS_URL` variable with a current, direct download link for the NYC `listings.csv.gz` from Inside Airbnb.
    *   Update `S3_BUCKET_NAME_AIRBNB` with the name of *your* S3 bucket created for this project.
    *   (Optional) Adjust `S3_PROCESSED_KEY_PREFIX`.
4.  **Install `pyarrow` in Airflow Workers (if not in your base Airflow image):**
    *   For development, you might need to `docker exec` into running `airflow-worker` and `airflow-scheduler` containers and run `pip install pyarrow`. For a more permanent solution, customize your Airflow Docker image.

### Running the Pipeline

1.  **Start Airflow Services:**
    ```bash
    docker-compose up -d
    ```
2.  **Access Airflow UI:** Open your browser to `http://localhost:8080` (login with `airflow`/`airflow` by default).
3.  **Run the DAG:**
    *   Find the DAG named `airbnb_nyc_data_pipeline_v3` (or your current `dag_id`).
    *   Unpause it using the toggle switch.
    *   Manually trigger the DAG by clicking the "play" (▶️) button.
    *   Monitor the progress in the Graph or Grid view.

### Verifying the Output ✅

1.  Check the Airflow Task Logs for each task to see detailed output and any errors.
2.  Files (`.gz`, `.csv`, `.parquet`) will be temporarily created in the `./dags/data_staging/` directory on your host machine (mapped from `/opt/airflow/dags/data_staging/` in the containers).
3.  Log into your AWS S3 Console and navigate to your target bucket (`S3_BUCKET_NAME_AIRBNB`). You should find the processed Parquet file under the `S3_PROCESSED_KEY_PREFIX` (e.g., `processed/airbnb_nyc_listings/YYYYMMDD_listings_processed.parquet`).

## Future Improvements 🚀

*   **Load to Data Warehouse/Query Engine:** Add tasks to load the processed Parquet from S3 into Amazon Redshift, Google BigQuery, or catalog it with AWS Glue for querying with Athena.
*   **Parameterization:** Use Airflow Variables or DAG Run Configuration to make the city, data URL, S3 bucket, etc., more dynamic.
*   **Data Quality Checks:** Implement tasks using tools like Great Expectations or custom Python checks to validate data at various stages.
*   **Cleanup Task:** Add a task to remove temporary files from the local staging area after successful S3 upload.
*   **More Sophisticated Error Handling & Alerting:** Implement Airflow's built-in alerting mechanisms (e.g., email on failure).

## Contact 👤

*   **Name:** [Your Name]
*   **LinkedIn:** [Your LinkedIn Profile URL]
*   **GitHub:** [Your GitHub Profile URL (this repo)]