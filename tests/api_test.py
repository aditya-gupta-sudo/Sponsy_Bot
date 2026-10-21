import requests

url = "https://jsonplaceholder.typicode.com/todos/1"

data = requests.get(url)

print(data.status_code)
print(data)
print(data.json()["title"])
print(data.json()["completed"])