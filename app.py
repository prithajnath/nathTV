import boto3
import os
import admin
import maya
import urllib.parse

from datetime import datetime, timedelta
from typing import Callable
from functools import partial
from models import db, User, Room, VideoProcessingTask
from celery import Celery, chain
from flask import (
    Flask,
    render_template,
    request,
    redirect,
)
from flask_bootstrap import Bootstrap
from flask_migrate import Migrate
from forms import LoginForm, DownloadClipForm
from uuid import uuid4

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

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
admin.register(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
Bootstrap(app)

kvs = boto3.client("kinesisvideo", region_name="us-west-2")

app.config["CELERY_BROKER_URL"] = os.getenv("CELERY_BROKER_URL")
app.config["CELERY_RESULT_BACKEND"] = os.getenv("CELERY_BROKER_URL")

celery = Celery("tasks", broker=app.config["CELERY_BROKER_URL"], backend=app.config["CELERY_RESULT_BACKEND"])
celery.conf.update(app.config)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


@app.route("/", methods=["GET"])
def index():
    if current_user.is_authenticated:
        rooms = []
        for room in Room.query.all():
            rooms.append({"id": room.id, "name": room.name})

        form = DownloadClipForm()
        return render_template("index.html", rooms=rooms, form=form)
    else:
        return redirect("/login")


@app.route("/akamai", methods=["GET"])
@login_required
def generate_akamai_link():
    id = request.args.get("room_id")
    room = Room.query.filter_by(id=int(id)).first()
    endpoint = kvs.get_data_endpoint(APIName="GET_HLS_STREAMING_SESSION_URL", StreamARN=room.stream_arn)["DataEndpoint"]

    kvam = boto3.client("kinesis-video-archived-media", endpoint_url=endpoint, region_name="us-west-2")
    response = kvam.get_hls_streaming_session_url(StreamARN=room.stream_arn, PlaybackMode="LIVE", Expires=6000)
    return redirect(
        f"https://players.akamai.com/players/hlsjs?streamUrl={urllib.parse.quote(response['HLSStreamingSessionURL'])}"
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    return render_template("profile.html")


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    form = LoginForm()
    return render_template("login.html", form=form)


@app.route("/download_clip", methods=["POST"])
@login_required
def download_clip():

    form = DownloadClipForm(formdata=request.form)
    print(form.data)
    if form.validate():
        start_datetime = form.start_datetime.data - timedelta(hours=5, minutes=30)
        end_datetime = form.end_datetime.data - timedelta(hours=5, minutes=30)
        room_id = request.args.get("room_id")
        room = Room.query.filter_by(id=int(room_id)).first()

        # send_video_url_to_user = last_task_in_chain(tasks.send_video_url_to_user)

        started_at_timestamp = datetime.now()
        video_task = VideoProcessingTask(
            room=room,
            user=current_user,
            status="in_queue",
            video_start_time=start_datetime,
            video_end_time=end_datetime,
            started_at=started_at_timestamp,
        )

        video_task.save_to_db(db)

        pipe = {
            "stream_arn": room.stream_arn,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "room": room.name,
            "email": current_user.email,
            "username": current_user.username,
            "task_id": video_task.id,
        }

        celery.send_task("download_archived_kinesis_clip", (pipe,))

        return render_template("file_is_being_downloaded.html", room=room.name, start=start_datetime, end=end_datetime)

    return "Download failed"


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user.verify_hash(form.password.data, user.password):
            login_user(user)
            if user.admin:
                return redirect("/admin")
            else:
                return redirect("/")

    return render_template("login.html", form=form)


@app.route("/tasks/<int:task_id>", methods=["GET"])
@app.route("/tasks", methods=["GET"])
@login_required
def tasks(task_id: int = None):
    if task_id:
        task = VideoProcessingTask.query.filter_by(user=current_user, id=task_id).first()
        _statuses = list(VideoProcessingTask.Status)
        statuses = [(_statuses[i].name, i <= task.status.value) for i in range(len(_statuses))]
        return render_template("tasks.html", task=task, statuses=statuses)
    else:
        _tasks = VideoProcessingTask.query.filter_by(user=current_user).order_by("started_at").all()
        tasks = [
            (
                task,
                maya.MayaDT.from_datetime(task.video_end_time).datetime(to_timezone="Asia/Calcutta"),
                maya.MayaDT.from_datetime(task.video_start_time).datetime(to_timezone="Asia/Calcutta"),
            )
            for task in _tasks
        ]
        return render_template("tasks.html", tasks=tasks)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="7000")
