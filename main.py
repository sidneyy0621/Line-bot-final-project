import os
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent, SourceUser, SourceGroup
from dotenv import load_dotenv
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import threading
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import ConflictingIdError
from pytz import timezone

load_dotenv()  # 載入 .env 檔案

# 初始化 Scheduler 並設定時區
taiwan_tz = timezone('Asia/Taipei')
scheduler = BackgroundScheduler(timezone=taiwan_tz)

# 啟動 Scheduler
scheduler.start()

app = Flask(__name__)

# 設定你的 LINE Bot 的 Channel Secret 和 Channel Access Token
LINE_CHANNEL_SECRET = os.getenv('your_channel_secret')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('your_channel_access_token')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Google Sheets API setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(os.getenv('your_json_keyfile'), scope)
client = gspread.authorize(creds)
sheet = client.open("linebot").sheet1

user_data = {}
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

# 提醒事項排程與通知
def schedule_reminder(text, interval, source_id):
    def reminder():
        while True:
            time.sleep(interval)
            reminder_message = f"您還有以下任務沒完成：\n{text}"
            notify_user(reminder_message, "提醒", source_id)
    
    reminder_thread = threading.Thread(target=reminder)
    reminder_thread.daemon = True
    reminder_thread.start()

def notify_user(message, title, source_id):
    try:
        lines = message.split('\n')
        if title == "提醒":
            if len(lines) < 5:
                raise IndexError("訊息行數不足")
            due_date = lines[1].split('：')[1].strip()
            content = lines[2].split('：')[1].strip()
            note = lines[3].split('：')[1].strip()
            assignee = lines[4].split('：')[1].strip()
            reminder_message = f"{title}：\n須完成日期：{due_date}\n預計完成內容：{content}\n註：{note}\n誰的工作：{assignee}"
        else:
            reminder_message = message
        line_bot_api.push_message(source_id, TextSendMessage(text=reminder_message))
    except IndexError as e:
        line_bot_api.push_message(source_id, TextSendMessage(text=f"提醒訊息格式錯誤，請確認輸入格式。錯誤：{e}"))
    except Exception as e:
        line_bot_api.push_message(source_id, TextSendMessage(text=f"發生錯誤：{e}"))

# 處理 LINE Bot 訊息事件
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

    user_id = event.source.user_id
    received_text = event.message.text

    if user_id not in user_data:
        user_data[user_id] = {'step': 0, 'account': '', 'password': ''}

    if received_text == "課表":
        user_data[user_id]['step'] = 1
        reply_text = "請輸入您的帳號?"
    elif user_data[user_id]['step'] == 1:
        user_data[user_id]['account'] = received_text
        user_data[user_id]['step'] = 2
        reply_text = "請輸入您的密碼?"
    elif user_data[user_id]['step'] == 2:
        user_data[user_id]['password'] = received_text
        user_data[user_id]['step'] = 3
        account = user_data[user_id]['account']
        password = user_data[user_id]['password']
        reply_text = get_course_schedule(account, password)  # 呼叫 get_course_schedule 函數取得課表
        user_data[user_id]['step'] = 0  # Reset the step after getting the schedule

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        print(f"Error: {e}")

    if text == "新增提醒":
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text="請依照以下格式上傳提醒："),
            TextSendMessage(text="須完成日期：YYYY/MM/DD\n預計完成內容：\n註：\n誰的工作：")
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
        delete_mode = True
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text="請輸入已完成的提醒內容："),
            TextSendMessage(text=list_reminders(False, source_id))
        ])

    elif text.startswith("完成提醒："):
        mark_reminder_as_completed(text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="提醒事項已標示為完成"))

    elif text == "定時提醒":
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text="請依照以下格式設定定時提醒："),
            TextSendMessage(text="定時提醒：\n須完成日期：YYYY/MM/DD\n預計完成內容：\n註：\n誰的工作：\n間隔時間：秒數")
        ])    
        
    elif text.startswith("定時提醒："):
        lines = text.split('\n')
        try:
            interval = int(lines[5].split('：')[1].strip())  # 直接使用秒數
            schedule_reminder('\n'.join(lines[1:6]), interval, source_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="定時提醒已設定"))
        except ValueError:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入有效的時間間隔（秒）"))

# 處理 LINE Bot 加入群組事件
@handler.add(JoinEvent)
def handle_join(event):
    line_bot_api.reply_message(event.reply_token, [
        TextSendMessage(text="大家好😲！我是你各位的提醒機器人，請輸入'新增提醒'來新增提醒事項。"),
        TextSendMessage(text="各位也可以在群組中討論事情喔！")
    ])

# 抓課表
def get_course_schedule(account, password):
    login_url = 'https://mobile.nkust.edu.tw/Account/Login'
    course_url = 'https://mobile.nkust.edu.tw/Student/Course'

    # 建立一個 session
    session = requests.Session()

    # 取得登入頁面，並解析 hidden 欄位
    login_page = session.get(login_url, verify=False)
    soup = BeautifulSoup(login_page.text, 'html.parser')
    hidden_inputs = soup.find_all("input", type="hidden")
    form = {x.get('name'): x.get('value') for x in hidden_inputs}

    # 添加登入資訊到表單
    form['Account'] = account
    form['Password'] = password

    # 登入
    response = session.post(login_url, data=form, verify=False)

    # 檢查是否登入成功
    if response.status_code == 200 and "登出" in response.text:
        course_page = session.get(course_url, verify=False)
        if course_page.status_code == 200:
            soup = BeautifulSoup(course_page.text, 'html.parser')
            table = soup.find('table', {'class': 'table'})
            if table:
                rows = table.find_all('tr')
                courses = []
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 10:
                        week_day = cols[8].text.strip()
                        course_name = cols[1].text.strip()
                        location = cols[9].text.strip()
                        courses.append((week_day, course_name, location))
                
                # 按照 week_day 中的中文數字排序
                chinese_numerals = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7}
                courses.sort(key=lambda x: chinese_numerals[x[0].split('(')[1].split(')')[0]])
                
                course_schedule = "\n".join([f"星期 {course[0]}, 課程名稱: {course[1]}, 地點: {course[2]}" for course in courses])
                return course_schedule
            else:
                return "找不到課表"
        else:
            return "無法訪問課表頁面"
    else:
        return "登入失敗"

def list_reminders(completed, source_id):
    try:
        # Fetch all records from Google Sheets
        records = sheet.get_all_records()
        result = []
        for record in records:
            if record["completed"] == '未完成':
                result.append(f"須完成日期：{record['due_date']}\n預計完成內容：{record['content']}\n註：{record['note']}\n誰的工作：{record['assignee']}")
        
        # Check if there are any reminders
        if result:
            return "\n\n".join(result)
        else:
            return "無未完成提醒"
    except gspread.exceptions.APIError as e:
        print(f"Google Sheets API 錯誤: {e}")
        return "無法從 Google Sheets 獲取記錄"
    except Exception as e:
        print(f"無法從 Google Sheets 獲取記錄: {e}")
        return "無法從 Google Sheets 獲取記錄"

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
    try:
        # Add reminder to Google Sheets
        sheet.append_row([due_date, content, note, assignee, "未完成", source_id])
        print("成功將記錄添加到 Google Sheets")
    except Exception as e:
        print(f"無法將記錄添加到 Google Sheets: {e}")

def delete_reminder(text):
    global reminders
    reminders = [reminder for reminder in reminders if not (
        f"須完成日期：{reminder['due_date']}\n預計完成內容：{reminder['content']}\n註：{reminder['note']}\n誰的工作：{reminder['assignee']}" == text
    )]
    try:
        # Delete reminder from Google Sheets
        cell = sheet.find(text.split('\n')[1].split('：')[1].strip())
        if cell:
            sheet.delete_rows(cell.row)
            print("成功將記錄從 Google Sheets 刪除")
    except Exception as e:
        print(f"無法將記錄從 Google Sheets 刪除: {e}")

def mark_reminder_as_completed(text):
    try:
        # Find the reminder in Google Sheets
        cell = sheet.find(text.split('\n')[1].split('：')[1].strip())
        if cell:
            # Update the 'completed' status to '已完成'
            sheet.update_cell(cell.row, 5, '已完成')
            print("成功將記錄標示為已完成")
    except Exception as e:
        print(f"無法將記錄標示為已完成: {e}")

# 每日提醒功能
def send_daily_reminders():
    try:
        # 獲取所有記錄
        records = sheet.get_all_records()
        now = datetime.now(taiwan_tz)
        today_date = now.strftime("%Y-%m-%d")  # 今日日期

        # 篩選未完成且日期未到的事項
        reminders_to_notify = []
        for record in records:
            due_date = record["due_date"]
            completed = record["completed"]

            # 只篩選未完成且日期未到的事項，無視是否已提醒
            if completed == "未完成" and due_date >= today_date:
                reminders_to_notify.append(record)

        # 整理提醒內容並推送
        if reminders_to_notify:
            for reminder in reminders_to_notify:
                reminder_text = (
                    f"🔸 須完成日期：{reminder['due_date']}\n"
                    f"內容：{reminder['content']}\n"
                    f"備註：{reminder['note']}\n"
                    f"負責人：{reminder['assignee']}\n\n"
                )
                group_id = reminder.get("group_id", "")
                if group_id:
                    print(f"推送提醒：{reminder_text}")  # 確保推送提醒的內容正確
                    send_personalized_notification(reminder_text, "提醒", group_id)

        else:
            print("無未完成事項需要提醒")
    except Exception as e:
        print(f"每日提醒功能錯誤：{e}")

# 確保排程任務只會執行一次
def setup_daily_reminder():
    try:
        # 檢查是否已有排程任務
        job = scheduler.get_job('daily_reminder')
        if not job:
            scheduler.add_job(send_daily_reminders, 'cron', hour=9, minute=35, id='daily_reminder', replace_existing=True)
            print("成功設置每日提醒排程")
        else:
            print("每日提醒排程任務已存在，跳過新增")
    except Exception as e:
        print(f"排程錯誤：{e}")

# 呼叫排程函數
setup_daily_reminder()

# 確保推送功能正常運行
# 推送通知功能
def send_personalized_notification(text, action, source_id):
    if not source_id:
        print("錯誤：無效的 group_id 或 user_id，無法推送訊息")
        return

    lines = text.split('\n')
    assignee = lines[3].split('：')[1].strip()
    try:
        if action == "新增":
            line_bot_api.push_message(source_id, TextSendMessage(text=f"@{assignee} 明天開始將會是充實的一天！😊\n{text}"))
        elif action == "提醒":
            line_bot_api.push_message(source_id, TextSendMessage(text=f"@{assignee} 你的工作完成了嗎?😒\n{text}"))
        print(f"已成功推送提醒訊息給 {source_id}")  # 確保訊息有成功推送
    except Exception as e:
        pass

if __name__ == "__main__":
    app.run(debug=True)