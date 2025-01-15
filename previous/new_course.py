import os
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv

load_dotenv()  # 載入 .env 檔案

app = Flask(__name__)

# 設定你的 LINE Bot 的 Channel Secret 和 Channel Access Token
LINE_CHANNEL_SECRET = os.getenv('your_channel_secret')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('your_channel_access_token')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

user_data = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    received_text = event.message.text

    if user_id not in user_data:
        user_data[user_id] = {'step': 0, 'account': '', 'password': ''}

    if received_text == "課表":
        user_data[user_id]['step'] = 1
        reply_text = "您的帳號?"
    elif user_data[user_id]['step'] == 1:
        user_data[user_id]['account'] = received_text
        user_data[user_id]['step'] = 2
        reply_text = "您的密碼?"
    elif user_data[user_id]['step'] == 2:
        user_data[user_id]['password'] = received_text
        user_data[user_id]['step'] = 3
        account = user_data[user_id]['account']
        password = user_data[user_id]['password']
        reply_text = get_course_schedule(account, password)  # 呼叫 get_course_schedule 函數取得課表
        user_data[user_id]['step'] = 0  # Reset the step after getting the schedule
    else:
        reply_text = f"你說的是: {received_text}"

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        print(f"Error: {e}")

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

if __name__ == "__main__":
    app.run(debug=True)