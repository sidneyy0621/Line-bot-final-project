import os
import google.generativeai as generativeai

generativeai.configure(api_key="AIzaSyAuiX0zdr7z4ef-lkuJVAJK2Llvle8kaBk")
response = generativeai.GenerativeModel("gemini-2.0-flash-exp").generate_content("你是誰?")
print(response.text)