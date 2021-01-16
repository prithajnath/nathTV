from celery import Celery
from botocore.exceptions import ClientError
from datetime import datetime
from time import sleep

import boto3
import os
import re
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
    with open(f"videos/{filename}", "wb") as f:
        for chunk in response["Payload"]:
            f.write(chunk)

    return {"filename": filename, "path": f"/usr/bin/cctv/videos/{filename}"}


@celery.task(name="s3.upload_video_to_s3")
def upload_video_to_s3(pipe: dict) -> str:
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

    return presigned_url
