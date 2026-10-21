import requests

url = "https://jsonplaceholder.typicode.com/posts"

data = {
    "reply": "Google is a strong potential sponsor.",
    "confidence": 0.91
}

response = requests.post(url, json = data)

print(response.status_code)
print(response.json())
