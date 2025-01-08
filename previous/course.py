import requests
from bs4 import BeautifulSoup

# 設定登入資訊
login_url = 'https://mobile.nkust.edu.tw/Account/Login'
course_url = 'https://mobile.nkust.edu.tw/Student/Course'
username = 'C112156219'
password = 'sz0419xi'

# 建立一個 session
session = requests.Session()

# 取得登入頁面，並解析 hidden 欄位
login_page = session.get(login_url, verify=False)
soup = BeautifulSoup(login_page.text, 'html.parser')
hidden_inputs = soup.find_all("input", type="hidden")
form = {x.get('name'): x.get('value') for x in hidden_inputs}

# 添加登入資訊到表單
form['Account'] = username
form['Password'] = password

# 登入
response = session.post(login_url, data=form, verify=False)

# 檢查是否登入成功
if response.status_code == 200 and "登出" in response.text:
    print("登入成功")
else:
    print("登入失敗")
    exit()

# 爬取課表頁面
response = session.get(course_url, verify=False)
if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    
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
        
        for course in courses:
            print(f"星期 {course[0]}, 課程名稱: {course[1]}, 地點: {course[2]}")
    else:
        print("找不到課表")
else:
    print("無法訪問課表頁面")
    

def get_course_schedule():
    response = session.get(course_url, verify=False)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
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
