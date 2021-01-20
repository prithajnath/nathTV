from celery import Celery, chain
from botocore.exceptions import ClientError
from datetime import datetime
from models import db, VideoProcessingTask, Room
from python_http_client.exceptions import HTTPError
from time import sleep
from app import app

import boto3
import os
import re
import sendgrid
import subprocess
import logging

VIDEO_OUTPUT_EXT = "mp4"

celery = Celery("tasks", broker=os.environ.get("CELERY_BROKER_URL"), backend=os.environ.get("CELERY_BROKER_URL"))

celery.conf.task_routes = {
    "video.*": {"queue": "video_queue"},
    "s3.*": {"queue": "s3_queue"},
}


@celery.task(name="video.fetch_stream_data")
def fetch_stream_data(pipe: dict, last_task_in_chain: bool = False) -> dict:
    with app.app_context():
        stream_arn = pipe["stream_arn"]
        room = pipe["room"]
        start_datetime = pipe["start_datetime"]
        end_datetime = pipe["end_datetime"]
        task_id = pipe["task_id"]

        task_obj = VideoProcessingTask.query.filter_by(id=task_id).first()
        task_obj.status = "fetching_hls_url"
        task_obj.updated_at = datetime.now()

        task_obj.save_to_db(db)

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
                "FragmentSelectorType": "SERVER_TIMESTAMP",
                "TimestampRange": {
                    "StartTimestamp": start_datetime,
                    "EndTimestamp": end_datetime,
                },
            },
        )

        timestamp = datetime.now()
        filename = re.sub("(-|:| |\.)", "_", f"{room}_{timestamp}") + f".{VIDEO_OUTPUT_EXT}"
        os.makedirs("videos", exist_ok=True)

        task_obj.updated_at = timestamp
        task_obj.status = "writing_hls_stream_to_file"
        task_obj.save_to_db(db)

        hls_url = kvam.get_hls_streaming_session_url(
            StreamARN=stream_arn,
            HLSFragmentSelector={
                "FragmentSelectorType": "PRODUCER_TIMESTAMP",
                "TimestampRange": {"StartTimestamp": start_datetime, "EndTimestamp": end_datetime},
            },
            PlaybackMode="ON_DEMAND",
            Expires=6000,
        )["HLSStreamingSessionURL"]

        # ffmpeg -i $url -c copy -bsf:a aac_adtstoasc output.mp4
        cmd = ["ffmpeg", "-i", hls_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", f"videos/{filename}"]
        logging.info(cmd)
        process = subprocess.Popen(cmd)

        stdout, stderr = process.communicate()

        if stderr:
            logging.error(stderr)

        return {**pipe, "filename": filename, "path": f"/usr/bin/cctv/videos/{filename}"}


@celery.task(name="s3.upload_video_to_s3")
def upload_video_to_s3(pipe: dict, last_task_in_chain: bool = False) -> dict:
    with app.app_context():
        path = pipe["path"]
        filename = pipe["filename"]
        task_id = pipe["task_id"]

        logging.info(f"received task to upload video {path} and generate a signed URL")

        task_obj = VideoProcessingTask.query.filter_by(id=task_id).first()
        task_obj.updated_at = datetime.now()
        task_obj.status = "uploading_file_to_s3"
        task_obj.save_to_db(db)

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
def send_video_url_to_user(pipe: dict, last_task_in_chain: bool = False) -> dict:
    with app.app_context():
        email = pipe["email"]
        username = pipe["username"]
        room = pipe["room"]
        start_datetime = pipe["start_datetime"]
        end_datetime = pipe["end_datetime"]
        video_url = pipe["presigned_url"]
        task_id = pipe["task_id"]

        logging.info(f"received task to send presigned URL {video_url} to {username}")

        task_obj = VideoProcessingTask.query.filter_by(id=task_id).first()
        task_obj.updated_at = datetime.now()
        task_obj.status = "emailing_video_to_user"
        task_obj.save_to_db(db)

        if os.getenv("ENV") == "production":
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
                if last_task_in_chain:
                    task_obj.status = "done"
                    task_obj.finished_at = datetime.now()
                    task_obj.save_to_db(db)

                return {**pipe, "email_status": response.status_code}
            except HTTPError as e:
                logging.error(e.to_dict)

        if last_task_in_chain:
            task_obj.status = "done"
            task_obj.finished_at = datetime.now()
            task_obj.save_to_db(db)

        return {**pipe, "email_status": 202}


@celery.task(name="download_archived_kinesis_clip")
def download_archived_kinesis_clip(pipe: dict) -> None:
    chain(
        fetch_stream_data.s(pipe),
        upload_video_to_s3.s(),
        send_video_url_to_user.s(last_task_in_chain=True),
    ).apply_async()
