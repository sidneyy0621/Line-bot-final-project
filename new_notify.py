import os
from datetime import datetime, timedelta
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent, SourceUser, SourceGroup
from linebot.exceptions import InvalidSignatureError
from flask import Flask, request, abort
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Line Bot API and Webhook Handler
# 請將 your_channel_secret 替換為你的 Channel Secret
line_bot_api = LineBotApi('W2csGypPz8dXqnt/nBvfOpHdbFcpMxlSh/lZBhPjhbenvACmhEA3KnoTku+AbWz8gHQMOTS0C6itjOWiiqM6pNnlbsY2MS4vdK+a17SNGybjC/3Q0xRFP4ovsQ+PgX7JvrW9ed8K0UXFGRU8G3GoVAdB04t89/1O/w1cDnyilFU=') # 請將 your_channel_access_token 替換為你的 Channel Access Token
handler = WebhookHandler('8b0b86eeb21a43e7a91dfcc70e658b4f') 

# Google Sheets API setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("savvy-folio-351502-7afc3bcb4050.json", scope)
client = gspread.authorize(creds)
sheet = client.open("linebot2025").sheet1

# In-memory storage for reminders
reminders = []
delete_mode = False

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

def list_reminders(completed, source_id):
    result = []
    for reminder in reminders:
        if reminder['completed'] == completed and reminder['source_id'] == source_id:
            result.append(f"須完成日期：{reminder['due_date']}\n預計完成內容：{reminder['content']}\n註：{reminder['note']}\n誰的工作：{reminder['assignee']}")
    return "\n\n".join(result)

def add_reminder(text, source_id):
    lines = text.split('\n')
    due_date = lines[0].split('：')[1].strip()
    content = lines[1].split('：')[1].strip()
    note = lines[2].split('：')[1].strip()
    assignee = lines[3].split('：')[1].strip()
    reminders.append({
        'due_date': due_date,
        'content': content,
        'note': note,
        'assignee': assignee,
        'completed': False,
        'group_id': source_id
    })

def delete_reminder(text):
    global reminders
    reminders = [reminder for reminder in reminders if not (
        f"須完成日期：{reminder['due_date']}\n預計完成內容：{reminder['content']}\n註：{reminder['note']}\n誰的工作：{reminder['assignee']}" == text
    )]

def notify_user(text, action, source_id):
    lines = text.split('\n')
    assignee = lines[3].split('：')[1].strip()
    if action == "新增":
        line_bot_api.push_message(source_id, TextSendMessage(text=f"@{assignee} 明天開始將會是充實的一天！😊\n{text}"))
    elif action == "提醒":
        line_bot_api.push_message(source_id, TextSendMessage(text=f"@{assignee} 你的工作完成了嗎?😒\n{text}"))

# user輸入文字時觸發
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global delete_mode
    text = event.message.text
    source = event.source

    if isinstance(source, SourceGroup):
        source_id = source.group_id
    elif isinstance(source, SourceUser):
        source_id = source.user_id
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="不支援此類型的對話。"))
        return

    if text == "新增提醒":
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text="請依照以下格式上傳提醒："),
            TextSendMessage(text="須完成日期：\n預計完成內容：\n註：\n誰的工作：")
        ])

    elif text == "刪除提醒":
        delete_mode = True
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text="請輸入要刪除的提醒內容："),
            TextSendMessage(text=list_reminders(False, source_id))
        ])

    elif text.startswith("須完成日期："):
        if delete_mode:
            delete_reminder(text)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已刪除提醒"))
            delete_mode = False
        else:
            add_reminder(text, source_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="提醒事項已新增"))
            notify_user(text, "新增", source_id)

    elif text == "未完成":
        reminders_text = list_reminders(False, source_id)
        if reminders_text:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reminders_text))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="無未完成提醒"))
    
    elif text == "已完成":
        reminders_text = list_reminders(True, source_id)
        if reminders_text:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reminders_text))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="無已完成提醒"))


# line bot 剛加入群組時觸發
@handler.add(JoinEvent)
def handle_join(event):
    line_bot_api.reply_message(event.reply_token, [
        TextSendMessage(text="大家好😲！我是你各位的提醒機器人，請輸入'新增提醒'來新增提醒事項。"),
        TextSendMessage(text="各位也可以在群組中討論事情喔！")
    ])


if __name__ == "__main__":
    app.run()