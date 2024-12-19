import os
import google.generativeai as generativeai
from dotenv import load_dotenv

load_dotenv()

generativeai.configure(api_key=os.getenv("KEY"))
response = generativeai.GenerativeModel('gemini-2.0-flash-exp').generate_content("who are you?")
print(response.text)