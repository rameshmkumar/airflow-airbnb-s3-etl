from __future__ import annotations
import pendulum
import os
import requests
import gzip
import shutil
import logging
import pandas as pd
import boto3
from airflow.models.dag import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError



NYC_LISTINGS_URL_CONFIG = "http://data.insideairbnb.com/united-states/ny/new-york-city/2025-05-01/data/listings.csv.gz" 


RAW_DATA_DIR = "/opt/airflow/data_staging"
RAW_GZ_FILENAME = "listings.csv.gz"
RAW_CSV_FILENAME = "listings.csv"
RAW_GZ_FILE_PATH_CONFIG = os.path.join(RAW_DATA_DIR, RAW_GZ_FILENAME) 
RAW_CSV_FILE_PATH_CONFIG = os.path.join(RAW_DATA_DIR, RAW_CSV_FILENAME)

PROCESSED_PARQUET_FILENAME="listings_processed.parquet"
PROCESSED_PARQUET_PATH=os.path.join(RAW_DATA_DIR, PROCESSED_PARQUET_FILENAME)


S3_BUCKET_NAME_CONFIG="rmkumar-airbnb-processed-data"
S3_PROCESSED_KEY_PREFIX="processed/airbnb_nyc_listings/"


def download_airbnb_data_callable(download_url:str, output_gz_file_path:str, output_csv_path: str, **kwargs):
    ti = kwargs['ti']
    
    logging.info(f"Starting download from {download_url}")

    output_dir=os.path.dirname(output_gz_file_path)
    os.makedirs(output_dir, exist_ok=True)

    try:
        
        response = requests.get(download_url, stream=True, timeout=300)
        response.raise_for_status()

        
        with open(output_gz_file_path, 'wb') as f:
            shutil.copyfileobj(response.raw, f)
        logging.info(f"Successfully downloaded and saved to {output_gz_file_path}")
        ti.xcom_push(key="downloaded_gz_file_path", value=output_gz_file_path)

        
        logging.info(f"Decompressing {output_gz_file_path} to {output_csv_path}")
        with gzip.open(output_gz_file_path, 'rb') as f_in: 
            with open(output_csv_path, 'wb') as f_out: 
                shutil.copyfileobj(f_in, f_out)
        logging.info(f"Successfully decompressed to {output_csv_path}")
        ti.xcom_push(key="downloaded_csv_file_path", value=output_csv_path)

    except requests.exceptions.RequestException as e:
        logging.error(f"Error during download: {e}", exc_info=True)
        raise
    except gzip.BadGzipFile as e:
        logging.error(f"Error decompressing file: {e}", exc_info=True)
        # If download was successful, downloaded_gz_file_path was already pushed.
        # If it failed before, nothing to push here related to gz.
        raise
    except Exception as e:
        logging.error(f"Unexpected error in download: {e}", exc_info=True)
        raise

def transform_airbnb_data(ti):
    logging.info("Starting data transformation")
    # Correct task_id for XCom pull to match the actual task_id of the download task
    raw_csv_filepath=ti.xcom_pull(task_ids='download_airbnb_raw_data', key='downloaded_csv_file_path')
    processed_parquet_file_path=PROCESSED_PARQUET_PATH

    if not raw_csv_filepath or not os.path.exists(raw_csv_filepath):
        logging.error(f"CSV file not found in XComs or path does not exist: {raw_csv_filepath}")
        raise FileNotFoundError(f"Input CSV file for transformation not found: {raw_csv_filepath}")

    logging.info(f"Reading raw data from {raw_csv_filepath}")

    try:
        df=pd.read_csv(raw_csv_filepath, low_memory=False)
        logging.info(f"Successfully read {raw_csv_filepath}. DataFrame shape: {df.shape}")

        logging.info("Starting data cleaning process")
        if 'price' in df.columns:
            df['price']=df['price'].astype(str)
            df['price_numeric']=pd.to_numeric(
                df['price'].str.replace(r'[$,]', '', regex=True),
                errors='coerce'
            )
            logging.info("Converted 'price' column into 'price_numeric'.")
        else:
            logging.warning("'price' column not found, 'price_numeric' will not be created.")

        # Verifying actual column names in your CSV
        date_columns=['last_scraped', 'host_since', 'calendar_last_scraped', 'first_review', 'last_review']
        for col in date_columns:
            if col in df.columns:
                df[col]=pd.to_datetime(df[col], errors='coerce')
                logging.info(f"Converted '{col}' to datetime")

        columns_to_keep = [
            'id', 'name', 'host_id', 'host_since', 'neighbourhood_cleansed',
            'latitude', 'longitude', 'property_type', 'room_type',
            'accommodates', 'bathrooms_text', 'bedrooms', 'beds', 
            'minimum_nights', 'maximum_nights', 'number_of_reviews', 'first_review',
            'last_review', 'review_scores_rating', 'instant_bookable'
        ]

        if 'price_numeric' in df.columns and 'price_numeric' not in columns_to_keep:
            columns_to_keep.append('price_numeric')

        existing_columns_to_keep=[col for col in columns_to_keep if col in df.columns]
        if not existing_columns_to_keep:
            logging.warning("No columns selected to keep after filtering. Output Parquet might be empty or cause errors.")
            

        df_transformed=df[existing_columns_to_keep].copy()

        for col in df_transformed.select_dtypes(include=['number']).columns:
            df_transformed[col]=df_transformed[col].fillna(0)

        for col in df_transformed.select_dtypes(include=['object', 'category']).columns:
            df_transformed[col]=df_transformed[col].fillna('Unknown')
        for col in df_transformed.select_dtypes(include=['datetime64[ns]']).columns:
            df_transformed[col]=df_transformed[col].fillna(pd.NaT)

        
        os.makedirs(os.path.dirname(processed_parquet_file_path), exist_ok=True)

        df_transformed.to_parquet(processed_parquet_file_path, index=False)
        logging.info(f"Successfully transformed data into parquet file and saved to {processed_parquet_file_path}")

        ti.xcom_push(key="processed_parquet_file_path", value=processed_parquet_file_path)
        return processed_parquet_file_path

    except pd.errors.EmptyDataError:
        logging.error(f"No data was found in {raw_csv_filepath}", exc_info=True)
        raise
    except Exception as e:
        logging.error(f"Error during data transformation: {e}", exc_info=True)
        raise

def upload_to_s3_bucket(ti, bucket_name:str, s3_key_prefix:str, **kwargs):

    processed_file_path=ti.xcom_pull(task_ids='transform_airbnb_listing_data', key='processed_parquet_file_path')
    task_instance_date_nodash=kwargs['ds_nodash']    #we store the task instance's date to use as file when we load into s3 bucket

    if not processed_file_path:
        logging.error("No processed data was found in Xcoms")
        raise ValueError("Processed file doesnt have data in it")
    if not os.path.exists(processed_file_path):
        logging.error(f"Processed file doesn't exists at path")
        raise FileNotFoundError("Processed file not found")
    
    file_name=os.path.basename(processed_file_path)  #from the path of processed_file_path we store the name as filename as string

    s3_object_key=os.path.join(s3_key_prefix,f"{task_instance_date_nodash}_{file_name}").replace("\\","/")  #created the s3_bucket_key name with combo of s3_key_prefix, task_ran_date, filename 
    logging.info(f"Attempting to upload {processed_file_path} to S3 bucket {bucket_name} as {s3_object_key}")

    try:
        s3_client=boto3.client('s3')
        s3_client.upload_file(processed_file_path, bucket_name, s3_object_key)  #takes the file from local and store into the bucket we gave with the give s3 key
        logging.info(f"Successfully uploaded '{s3_object_key} to s3 bucket '{bucket_name}'")

        ti.xcom_push(key="s3_processed_data_key", value=f"s3://{bucket_name}/{s3_object_key}") #we pushed the url of the file we uploaded into AWS S3 bucket

        return f"s3://{bucket_name}/{s3_object_key}"
    
    except NoCredentialsError:
        logging.error("Upload failed: AWS credentials not found by Boto3")
        raise
    except PartialCredentialsError:
        logging.error("Incomplete/Incorrect credentials found by Boto3")
        raise
    except ClientError as e:
        logging.error(f"S3 Clienterror during upload of '{s3_object_key}':{e} ")
        raise
    except Exception as e:
        logging.error(f"An unexpected error has been caugt {e}")
        raise
    




default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1, 
    'retry_delay': pendulum.duration(minutes=2),
}

with DAG(
    dag_id='airbnb_nyc_data_pipeline_v1',
    default_args=default_args,
    description='ETL pipeline for NYC Airbnb listings: Download, Decompress, Transform & Load to S3',
    schedule='@once',
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"), 
    catchup=False,
    tags=['airbnb', 'etl', 'nyc', 'portfolio', 'extract', 's3'],
) as dag:

    start_pipeline = EmptyOperator(
        task_id='start_pipeline',
    )

    task_download_airbnb_data = PythonOperator(
        task_id='download_airbnb_raw_data',
        python_callable=download_airbnb_data_callable,
        op_kwargs={
            'download_url': NYC_LISTINGS_URL_CONFIG, 
            'output_gz_file_path': RAW_GZ_FILE_PATH_CONFIG, 
            'output_csv_path': RAW_CSV_FILE_PATH_CONFIG 
        }
    )

    task_transform_airbnb_data=PythonOperator(
        task_id='transform_airbnb_listing_data', 
        python_callable=transform_airbnb_data,
    )

    task_upload_to_s3=PythonOperator(
        task_id='Upload_processed_parquet_to_s3',
        python_callable=upload_to_s3_bucket,
        op_kwargs={'bucket_name':S3_BUCKET_NAME_CONFIG,
                   's3_key_prefix':S3_PROCESSED_KEY_PREFIX}
    )

    end_pipeline = EmptyOperator(
        task_id='end_pipeline',
    )

    start_pipeline >> task_download_airbnb_data >> task_transform_airbnb_data >> task_upload_to_s3 >> end_pipeline