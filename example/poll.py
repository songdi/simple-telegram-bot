"""
run in terminal: python -m example.poll.py
"""
import logging

from telegrambotclient import bot_client
from telegrambotclient.base import Message, Poll, PollAnswer, PollType

from example.settings import BOT_TOKEN

logger = logging.getLogger("telegram-bot-client")
logger.setLevel(logging.DEBUG)

router = bot_client.router()
example_bot = bot_client.create_bot(token=BOT_TOKEN, router=router)
example_bot.delete_webhook(drop_pending_updates=True)


@router.command_handler(cmds=("/vote", ))
def on_show_vote_poll(bot, message: Message):
    bot.send_poll(
        chat_id=message.chat.id,
        question="regular vote",
        options=("option 1", "option 2", "option 3"),
    )


@router.poll_handler()
def on_poll_state(bot, poll: Poll):
    print("receive a vote on {0}".format(poll.options))


@router.command_handler(cmds=("/quiz", ))
def on_show_quiz_poll(bot, message: Message):
    bot.send_poll(
        chat_id=message.chat.id,
        question="quiz",
        options=("answer 1", "answer 2", "answer 3"),
        is_anonymous=False,
        type=PollType.QUIZ,
        correct_option_id=2,
    )


@router.poll_answer_handler()
def on_poll_answer(bot, poll_answer: PollAnswer):
    bot.send_message(chat_id=poll_answer.user.id,
                     text="you select: {0}".format(poll_answer.option_ids))
    print(poll_answer)


example_bot.run_polling(timeout=10)
