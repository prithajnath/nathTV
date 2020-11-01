import boto3
import os
import urllib.parse

from datetime import datetime
from models import db
from flask import Flask, render_template
from flask_migrate import Migrate

app = Flask(__name__)
app.config.update(
    dict(
        DEBUG=False if os.environ.get("ENV") == "production" else True,
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=True,
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        CSRF_ENABLED=True,
    )
)

db.init_app(app)
migrate = Migrate(app, db)

hls_stream_ARN = os.getenv("HLS_STREAM_ARN")
STREAM_NAME = os.getenv("HLS_STREAM_NAME")
kvs = boto3.client("kinesisvideo", region_name="us-west-2")


@app.route("/", methods=["GET"])
def index():
    endpoint = kvs.get_data_endpoint(
        APIName="GET_HLS_STREAMING_SESSION_URL", StreamARN=hls_stream_ARN
    )["DataEndpoint"]

    kvam = boto3.client(
        "kinesis-video-archived-media", endpoint_url=endpoint, region_name="us-west-2"
    )
    response = kvam.get_hls_streaming_session_url(
        StreamARN=hls_stream_ARN, PlaybackMode="LIVE", Expires=6000
    )
    return render_template(
        "index.html", src=urllib.parse.quote(response["HLSStreamingSessionURL"])
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="7000")
