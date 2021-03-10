import os
import re
from enum import IntEnum
from functools import partial
from typing import Union

import aiotg
from sqlalchemy.sql.functions import now

from tasksbot.models import Task
from tasksbot.models.chat import Chat

bot = aiotg.Bot(api_token=os.environ.get('TG_BOT_TOKEN', ''))


class ChatState(IntEnum):
    NORMAL = 0
    EXPECT_TASK = 1
    EXPECT_PERIOD = 2


GREETING_BY_STATE = [
    '',
    'Вводи новое дело',
    "Вводи период"
]


@bot.command(r"^/start")
async def start(chat: aiotg.Chat, match):
    db_chat = await Chat.query.where(Chat.chat_id == str(chat.id)).gino.first()
    if not db_chat:
        await Chat.create(chat_id=str(chat.id), chat_state=ChatState.EXPECT_TASK)
        return chat.reply('Привет. Начни с того что сразу введи дело.')
    return chat.reply(f'Рад видеть тебя снова {GREETING_BY_STATE[db_chat.chat_state]}')


async def make_menu_markup(chat: aiotg.Chat):
    t: Union[Task, None] = None
    return {
        'inline_keyboard':
            [
                [
                    {
                        'text': "📝 Добавить дело",
                        'callback_data': 'new'
                    },
                    {
                        'text': "⚙️ Время уведомлений",
                        'callback_data': 'setup/time'
                    }
                ]
            ] + [
                [
                    {
                        'text': f'➡️{t.content}',
                        'callback_data': f'mark/{t.id}'
                    },
                    {
                        'text': "🔧⏰",
                        'callback_data': f'time/{t.id}'
                    },
                    {
                        'text': "🗑",
                        'callback_data': f'delete/{t.id}'
                    }
                ]
                for t in await Task.query.where(Task.chat_id == str(chat.id)).gino.all()

            ]
    }


@bot.command(r"^/menu")
async def menu(chat: aiotg.Chat, match):
    markup = await make_menu_markup(chat)
    chat.reply("Выбери действие:", markup=markup)


def plural(number: int, one: str, two: str, many: str):
    if 5 < number < 20:
        return many
    number = number % 10
    if number == 1:
        return one
    if number < 5:
        return two
    return many


plural_days = partial(plural, one="день", two="дня", many="дней")


@bot.default
async def message(chat: aiotg.Chat, match):
    db_chat: Chat = await Chat.query.where(Chat.chat_id == str(chat.id)).gino.first()
    if not db_chat:
        db_chat: Chat = await Chat.create(chat_id=str(chat.id), chat_state=ChatState.EXPECT_TASK)
    if db_chat.chat_state == ChatState.EXPECT_TASK:
        editing_task = await Task.create(
            content=chat.message['text'],
            message_id=str(chat.message['message_id']),
            chat_id=str(chat.id)
        )
        await db_chat.update(
            chat_state=ChatState.EXPECT_PERIOD,
            editing_task_id=editing_task.id
        ).apply()
        return chat.reply('Теперь введите периодичность в днях (просто целое число!)')
    elif db_chat.chat_state == ChatState.EXPECT_PERIOD and db_chat.editing_task_id:
        try:
            period = int(chat.message['text'])
        except Exception:
            return chat.reply('Что-то не очень похоже на число. что то типа "5" я бы понял, но не это.')
        await db_chat.update(chat_state=ChatState.NORMAL).apply()
        task: Task = await Task.get(db_chat.editing_task_id)
        await task.update(period_days=period).apply()

        return chat.reply(f'Устанавливлен период {period} {plural_days(period)}.')

    return chat.reply('не ожидал что ты что-то мне '
                      'тут напишешь без предупреждения '
                      '(без запроса). Или я что-то не понял.')


@bot.callback(r'new')
async def callback_new(chat: aiotg.Chat, cb, match):
    db_chat: Chat = await Chat.query.where(Chat.chat_id == str(chat.id)).gino.first()
    await db_chat.update(chat_state=ChatState.EXPECT_TASK).apply()
    chat.send_text(GREETING_BY_STATE[db_chat.chat_state])


@bot.callback(r'mark/(\d+)')
async def callback_mark_as_done(chat: aiotg.Chat, cb, match: re.Match):
    task: Task = await Task.query.where(Task.id == int(match.group(1))).gino.first()
    if not task:
        return chat.send_text(f"Странно, но такой задачи у меня нет (ИД={task.id})")

    await task.update(
        done_mark_user_id=str(cb.src['from']['id']),
        last_done_time=now()
    ).apply()
    chat.send_text(f'Задача "{task.content}" отмечена как выполнена. '
                   f'Следующий раз напомню через {task.period_days} {plural_days(task.period_days)}')
