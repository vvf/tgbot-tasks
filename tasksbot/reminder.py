import asyncio
import logging
from datetime import datetime, timedelta, time
from functools import partial

from tasksbot.bot import bot
from tasksbot.models import Task, Chat

logger = logging.getLogger(__name__)
loop = asyncio.get_event_loop()


def reminder_loop(n=0):
    loop.create_task(remind_all(n), name=f"reminder_{n}")
    loop.call_later(60, reminder_loop, n + 1)


def make_task_menu(task: Task):
    return bot.json_serialize({
        'inline_keyboard':
            [[{
                'text': f'Сделано ️✅',
                'callback_data': f'mark/{task.id}'
            }]]
    })


async def send_task_notify(task: Task, chat: Chat = None):
    message = await bot.send_message(
        task.chat_id, task.content,
        reply_to_message_id=task.message_id,
        reply_markup=make_task_menu(task)
    )
    notify_time = datetime.combine(
        (datetime.now() + timedelta(days=task.period_days)).date(),
        task.notify_time.time()
    )
    await task.update(
        last_notify_id=str(message['result']['message_id']),
        notify_time=notify_time
    ).apply()


async def remind_all(n=0):
    await loop.run_in_executor(None, partial(logger.info, "Check tasks to remind (%5d)", n))
    chats = await Chat.query.where(Chat.notify_next_date_time <= datetime.now()).gino.all()
    if not chats:
        return
    chats_by_ids = {chat.chat_id: chat for chat in chats}
    tasks = await Task.query.where(
        Task.chat_id.in_(chats_by_ids.keys()) &
        (Task.notify_time <= datetime.combine(datetime.now(), time(0, 0))) &
        (Task.exact_in_time == False)
    ).gino.all()
    tasks += await Task.query.where(
        (Task.notify_time <= datetime.now()) &
        Task.exact_in_time
    ).gino.all()
    if not tasks:
        await mark_chats_as_processed(chats)
        return

    await asyncio.gather(*[
        send_task_notify(task, chats_by_ids[task.chat_id], )
        for task in tasks
    ])
    await mark_chats_as_processed(chats)


async def mark_chats_as_processed(chats: list[Chat]):
    chat: Chat = None
    for chat in chats:
        notify_time = chat.notify_next_date_time.time()
        await chat.update(
            notify_next_date_time=datetime.combine(
                (datetime.now() + timedelta(days=1)).date(),
                notify_time
            )
        ).apply()
