"""
run in terminal: python example.document
"""
from telegrambotclient import TelegramBot, bot_client
from telegrambotclient.base import InputFile, Message

from example.settings import BOT_TOKEN

router = bot_client.router()
example_bot = bot_client.create_bot(token=BOT_TOKEN, router=router)
example_bot.delete_webhook(drop_pending_updates=True)


@router.message_handler()
def on_document(bot: TelegramBot, message: Message):
    # InputFile can accept a file path string
    thumb_img = InputFile("thumb.jpg", "<path-to-image-file>")
    file_name = "<path-to-file>"
    # document can be a URL
    # document = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    # document can be a InputFile
    # document = InputFile("sample.txt", file_name)
    with open(file_name, "rb") as file_obj:
        # InputFile can accept a bytes stream as well
        document = InputFile("sample.txt", file_obj.read())
        bot.send_document(chat_id=message.chat.id,
                          document=document,
                          thumb=thumb_img)


example_bot.run_polling(timeout=10)
