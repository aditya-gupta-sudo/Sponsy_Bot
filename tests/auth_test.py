import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("API_KEY")

headers = {
    "Authorization": f"Bearer {api_key}"
}

url = "https://httpbin.org/headers"

response = requests.get(url, headers=headers)

print(response.status_code)
print(response.json())