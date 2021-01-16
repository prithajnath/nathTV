from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.fields.html5 import DateTimeLocalField
from wtforms.validators import Required, InputRequired, Length


class LoginForm(FlaskForm):
    username = StringField(
        "username", validators=[InputRequired(), Length(min=4, max=200)]
    )
    password = PasswordField(
        "password", validators=[InputRequired(), Length(min=8, max=80)]
    )
    remember = BooleanField("remember")


class DownloadClipForm(FlaskForm):
    start_datetime = DateTimeLocalField(
        "start_time", validators=[Required()], format="%Y-%m-%dT%H:%M"
    )
    end_datetime = DateTimeLocalField(
        "end_time", validators=[Required()], format="%Y-%m-%dT%H:%M"
    )

    # def __init__(self, start_datetime, end_datetime):
    #     self.start_datetime = start_datetime
    #     self.end_datetime = end_datetime
