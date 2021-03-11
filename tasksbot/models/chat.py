from tasksbot.database import db


class Chat(db.Model):
    __tablename__ = 'chat'

    chat_id = db.Column(db.String(255), primary_key=True)
    chat_name = db.Column(db.String(255), default='')
    chat_state = db.Column(db.Integer, default=0)
    editing_task_id = db.Column(db.ForeignKey("task.id"), index=True, nullable=True)
    notify_next_date_time = db.Column(db.DateTime(), index=True)

    def __str__(self):
        return self.chat_name

