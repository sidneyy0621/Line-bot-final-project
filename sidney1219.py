import os
import google.generativeai as generativeai
from dotenv import load_dotenv

load_dotenv()

generativeai.configure(api_key=os.getenv("your_api_key_here"))
response = generativeai.GenerativeModel("gemini-2.0-flash-exp").generate_content("Do u nkow NKUST?")
print(response.text)