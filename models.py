from flask_sqlalchemy import SQLAlchemy
from passlib.hash import pbkdf2_sha256
from mixins import dbMixin
from enum import Enum
from flask_login import UserMixin
from uuid import uuid1

db = SQLAlchemy()


class User(dbMixin, UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), nullable=True, unique=True)
    username = db.Column(db.String(20), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    admin = db.Column(db.Boolean, default=False)

    def __init__(self, username="test", password="test", admin=False):
        self.username = username
        self.password = pbkdf2_sha256.hash(password)
        self.admin = admin

    def verify_hash(self, password, hash):
        return pbkdf2_sha256.verify(password, hash)

    def set_password(self, password):
        self.password = pbkdf2_sha256.hash(password)

    def __str__(self):
        return self.username

    __repr__ = __str__


class Room(db.Model, dbMixin):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    stream_arn = db.Column(db.String(200), nullable=False)
    stream_name = db.Column(db.String(200), nullable=False)

    def __str__(self):
        return self.name

    __repr__ = __str__


class VideoProcessingTask(db.Model, dbMixin):
    __tablename__ = "video_processing_tasks"

    class Status(Enum):
        in_queue = 0
        fetching_hls_url = 1
        writing_hls_stream_to_file = 2
        uploading_file_to_s3 = 3
        emailing_video_to_user = 4
        done = 5

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.Enum(Status))
    video_start_time = db.Column(db.DateTime)
    video_end_time = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    room = db.relationship("Room")
    user = db.relationship("User")
