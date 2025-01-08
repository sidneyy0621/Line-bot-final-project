import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from course import get_course_schedule  # 匯入 course.py 中的 get_course_schedule 函數

app = Flask(__name__)

LINE_CHANNEL_SECRET = 'bac7c9b32606fec4d5a74c9dca80eb9b'
LINE_CHANNEL_ACCESS_TOKEN = 'wrtAKskRx/HK6GFU7/1Cur3rU57ieem3lS2jrSyAlQN8x0nxJi4xtlMlk7+DpQ1f+Ea4VEQs6P2BfdlbNj99S0CG24wUmR6YKNWUDy9WQaxIXO+jUjy5DfIudJInjzghPvv2e9WpcUDv56WXaXeFYAdB04t89/1O/w1cDnyilFU='

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    # 確認請求來自 LINE 平台
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 簡單的對談邏輯
    received_text = event.message.text
    if received_text == "課表":
        reply_text = get_course_schedule()  # 呼叫 get_course_schedule 函數取得課表
    else:
        reply_text = f"你說的是: {received_text}"

    # 回應收到的訊息
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        app.logger.error(f"Error: {e}")

if __name__ == "__main__":
    app.run(debug=True)
