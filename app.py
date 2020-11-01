import boto3
import os
import admin
import urllib.parse

from datetime import datetime
from models import db, User, Room
from flask import Flask, render_template, request, redirect
from flask_bootstrap import Bootstrap
from flask_migrate import Migrate
from forms import LoginForm

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


hls_stream_ARN = os.getenv("HLS_STREAM_ARN")
STREAM_NAME = os.getenv("HLS_STREAM_NAME")
kvs = boto3.client("kinesisvideo", region_name="us-west-2")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


@app.route("/", methods=["GET"])
def index():
    if current_user.is_authenticated:
        rooms = []
        for room in Room.query.all():
            rooms.append({'id': room.id, 'name': room.name})
        return render_template('index.html', rooms=rooms)
    else:
        return redirect("/login")

@app.route("/akamai", methods=["GET"])
def generate_akamai_link():

    id = request.args.get("room_id")
    room = Room.query.filter_by(id=int(id)).first()
    endpoint = kvs.get_data_endpoint(
        APIName="GET_HLS_STREAMING_SESSION_URL", StreamARN=room.stream_arn
    )["DataEndpoint"]

    kvam = boto3.client(
        "kinesis-video-archived-media", endpoint_url=endpoint, region_name="us-west-2"
    )
    response = kvam.get_hls_streaming_session_url(
        StreamARN=room.stream_arn, PlaybackMode="LIVE", Expires=6000
    )
    return redirect(
        f"https://players.akamai.com/players/hlsjs?streamUrl={urllib.parse.quote(response['HLSStreamingSessionURL'])}"
    )

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    return render_template("profile.html")

@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    form = LoginForm()
    return render_template("login.html", form=form)

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



if __name__ == "__main__":
    app.run(host="0.0.0.0", port="7000")