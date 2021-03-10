from datetime import datetime, timedelta

from tasksbot.database import db


def now_plus_day():
    return datetime.now() + timedelta(days=1)


class Task(db.Model):
    __tablename__ = 'task'

    id = db.Column(db.Integer(), primary_key=True)
    chat_id = db.Column(db.ForeignKey("chat.chat_id"), index=True)
    content = db.Column(db.String(1024), default='')
    message_id = db.Column(db.String(128), default='', index=True)
    last_notify_id = db.Column(db.String(128), default='', index=True)
    period_days = db.Column(db.Integer, default=1)
    last_done_time = db.Column(db.DateTime(), default=now_plus_day)
    notify_time = db.Column(db.DateTime(), default=now_plus_day)
    done_mark_user_id = db.Column(db.String(128), default='', index=True)
