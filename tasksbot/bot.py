import asyncio
import os
import re
from datetime import datetime, timedelta
from enum import IntEnum
from functools import partial
from typing import Union

import aiotg
from sqlalchemy.sql.functions import now

from tasksbot.models import Task
from tasksbot.models.chat import Chat

bot = aiotg.Bot(
    api_token=os.environ.get('TG_BOT_TOKEN', ''),
    default_in_groups=True,
)


class ChatState(IntEnum):
    NORMAL = 0
    EXPECT_TASK = 1
    EXPECT_PERIOD = 2
    EXPECT_TIME_WHEN_SEND_NOTIFY = 3
    EXPECT_TASK_TIME_WHEN_SEND_NOTIFY = 4


GREETING_BY_STATE = [
    '',
    'Вводи новое дело',
    "Вводи период",
    "Введи время когда присылать уведомление (ЧЧ:ММ)"
    "Введи время когда присылать уведомление (ЧЧ:ММ)"
]


@bot.command(r"^/start")
async def start(chat: aiotg.Chat, match):
    db_chat: Chat = await Chat.get(str(chat.id))
    if not db_chat:
        db_chat: Chat = await create_chat_in_db(chat)
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


def get_chat_title(chat: aiotg.Chat):
    return chat.message['chat'].get('title') or chat.message['chat'].get('username')


@bot.default
async def message(chat: aiotg.Chat, match):
    db_chat: Chat = await Chat.get(str(chat.id))
    if not db_chat:
        db_chat: Chat = await create_chat_in_db(chat)
    if chat.message['chat']['type'] == 'group':
        pass
    if db_chat.chat_state == ChatState.EXPECT_TIME_WHEN_SEND_NOTIFY:
        try:
            hours, minutes = map(int, chat.message['text'].split(':'))
            from datetime import time
            time = time(hours, minutes, 0)
        except Exception:
            return chat.reply('Что-то не очень похоже на время. что то типа "12:22" я бы понял.')
        await db_chat.update(
            chat_state=ChatState.NORMAL,
            notify_next_date_time=datetime.combine(
                db_chat.notify_next_date_time.date(), time
            ),
            editing_task_id=None
        ).apply()
        return chat.reply(f'Устновлено время уведомления - {time:%H:%M}')
    elif db_chat.chat_state == ChatState.EXPECT_TASK:
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
        task: Task = await Task.get(db_chat.editing_task_id)
        await db_chat.update(chat_state=ChatState.NORMAL, editing_task_id=None).apply()
        if not task:
            chat.reply(f"Уже такой задачи нет. ({db_chat.editing_task_id})")
        await task.update(period_days=period).apply()

        return chat.send_text(
            f'Устанавливлен период {period} {plural_days(period)}.',
            reply_to_message_id=task.message_id
        )

    return chat.reply('не ожидал что ты что-то мне '
                      'тут напишешь без предупреждения '
                      '(без запроса). Или я что-то не понял.')


@bot.callback(r'new')
async def callback_new(chat: aiotg.Chat, cb, match):
    db_chat: Chat = await Chat.get(str(chat.id))
    await db_chat.update(chat_state=ChatState.EXPECT_TASK).apply()
    text = GREETING_BY_STATE[db_chat.chat_state]
    await asyncio.gather(chat.send_text(text), cb.answer(text=text, show_alert=False))


@bot.callback(r'setup/time')
async def callback_new(chat: aiotg.Chat, cb, match):
    db_chat: Chat = await Chat.get(str(chat.id))
    await db_chat.update(chat_state=ChatState.EXPECT_TIME_WHEN_SEND_NOTIFY).apply()
    text = f"Сейчас время уведомлений {db_chat.notify_next_date_time.time():%H:%M}.\nВведи новое время уведомлений в формате Ч:М"
    await asyncio.gather(chat.send_text(text), cb.answer(text=text, show_alert=False))


@bot.callback(r'mark/(\d+)')
async def callback_mark_task_as_done(chat: aiotg.Chat, cb: aiotg.CallbackQuery, match: re.Match):
    task: Task = await Task.get(int(match.group(1)))
    if not task:
        text = f"Странно, но такой задачи у меня нет (ИД={task.id})"
        return await cb.answer(text=text, show_alert=True)

    await task.update(
        done_mark_user_id=str(cb.src['from']['id']),
        last_done_time=now()
    ).apply()
    text = f'Задача "{task.content}" отмечена как выполнена. ' \
           f'Следующий раз напомню через {task.period_days} {plural_days(task.period_days)}'
    await cb.answer(text=text, show_alert=True)


@bot.callback(r'time/(\d+)')
async def callback_set_new_perio(chat: aiotg.Chat, cb: aiotg.CallbackQuery, match: re.Match):
    task: Task = await Task.get(int(match.group(1)))
    db_chat: Chat = await Chat.get(str(chat.id))
    if not task:
        text = f"Странно, но такой задачи у меня нет (ИД={task.id})"
        return await cb.answer(text=text, show_alert=True)

    await db_chat.update(
        chat_state=ChatState.EXPECT_PERIOD,
        editing_task_id=task.id
    ).apply()
    text = f"Теперь введите периодичность в днях (просто целое число!) для задачи \"{task.content}\""
    await asyncio.gather(chat.send_text(text), cb.answer(text=text, show_alert=False))


@bot.callback(r'delete/(\d+)')
async def callback_delete_task(chat: aiotg.Chat, cb: aiotg.CallbackQuery, match: re.Match):
    task: Task = await Task.get(int(match.group(1)))
    if not task:
        text = f"Странно, но такой задачи у меня нет (ИД={task.id})"
        return await cb.answer(text=text, show_alert=True)

    await task.delete()
    text = f'Задача удалена'
    markup = await make_menu_markup(chat)
    await asyncio.gather(
        chat.edit_reply_markup(chat.message['message_id'], markup=markup),
        cb.answer(text=text, show_alert=True),
        chat.send_text(text, reply_to_message_id=task.message_id)
    )


async def create_chat_in_db(chat: aiotg.Chat, chat_state=ChatState.EXPECT_TASK) -> Chat:
    db_chat: Chat = await Chat.create(
        chat_id=str(chat.id),
        chat_name=get_chat_title(chat),
        chat_state=chat_state,
        notify_next_date_time=datetime.now() + timedelta(days=1)
    )
    return db_chat
