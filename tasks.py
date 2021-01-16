from celery import Celery
from botocore.exceptions import ClientError
from datetime import datetime
from python_http_client.exceptions import HTTPError
from time import sleep

import boto3
import os
import re
import sendgrid
import logging

celery = Celery("tasks", broker=os.environ.get("CELERY_BROKER_URL"), backend=os.environ.get("CELERY_BROKER_URL"))

celery.conf.task_routes = {
    "video.*": {"queue": "video_queue"},
    "s3.*": {"queue": "s3_queue"},
}


@celery.task(name="video.fetch_stream_data")
def fetch_stream_data(pipe: dict) -> dict:
    stream_arn = pipe["stream_arn"]
    room = pipe["room"]
    start_datetime = pipe["start_datetime"]
    end_datetime = pipe["end_datetime"]

    logging.info(f"received task to download video {stream_arn}")
    kvs = boto3.client("kinesisvideo", region_name="us-west-2")
    endpoint = kvs.get_data_endpoint(APIName="GET_CLIP", StreamARN=stream_arn)["DataEndpoint"]
    kvam = boto3.client(
        "kinesis-video-archived-media",
        endpoint_url=endpoint,
        region_name="us-west-2",
    )

    response = kvam.get_clip(
        StreamARN=stream_arn,
        ClipFragmentSelector={
            "FragmentSelectorType": "PRODUCER_TIMESTAMP",
            "TimestampRange": {
                "StartTimestamp": start_datetime,
                "EndTimestamp": end_datetime,
            },
        },
    )

    room = re.sub("(-|:| |\.)", "_", room)
    timestamp = re.sub("(-|:| |\.)", "_", datetime.now().__str__())
    filename = f"{room}_{timestamp}.mp4"
    os.makedirs("videos", exist_ok=True)
    with open(f"videos/{filename}", "wb") as f:
        for chunk in response["Payload"]:
            f.write(chunk)

    return {**pipe, "filename": filename, "path": f"/usr/bin/cctv/videos/{filename}"}


@celery.task(name="s3.upload_video_to_s3")
def upload_video_to_s3(pipe: dict) -> dict:
    path = pipe["path"]
    filename = pipe["filename"]
    logging.info(f"received task to upload video {path} and generate a signed URL")
    s3 = boto3.resource("s3")
    try:
        s3.meta.client.upload_file(path, os.getenv("VIDEO_BUCKET_NAME"), filename)
    except ClientError as e:
        print(e)

    s3_client = boto3.client("s3")
    try:
        presigned_url = s3_client.generate_presigned_url(
            "get_object", Params={"Bucket": os.getenv("VIDEO_BUCKET_NAME"), "Key": filename}, ExpiresIn=3600
        )
    except ClientError as e:
        print(e)

    return {**pipe, "presigned_url": presigned_url}


@celery.task(name="s3.send_video_url_to_user")
def send_video_url_to_user(pipe: dict) -> dict:
    email = pipe["email"]
    username = pipe["username"]
    room = pipe["room"]
    start_datetime = pipe["start_datetime"]
    end_datetime = pipe["end_datetime"]
    video_url = pipe["presigned_url"]

    logging.info(f"received task to send presigned URL {video_url} to {username}")

    sg = sendgrid.SendGridAPIClient(api_key=os.environ.get("SENDGRID_API_KEY"))
    template_id = os.environ.get("SENDGRID_S3_VIDEO_URL_TEMPLATE_ID")
    data = {
        "from": {"email": "prithaj.nath@theangrydev.io"},
        "personalizations": [
            {
                "to": [{"email": email}],
                "subject": "Your video is ready",
                "dynamic_template_data": {
                    "username": username,
                    "room": room,
                    "start": start_datetime,
                    "end": end_datetime,
                    "video_url": video_url,
                },
            }
        ],
        "template_id": template_id,
    }

    try:
        response = sg.client.mail.send.post(request_body=data)
    except HTTPError as e:
        logging.error(e.to_dict)

    return {**pipe, "email_status": response.status_code}
