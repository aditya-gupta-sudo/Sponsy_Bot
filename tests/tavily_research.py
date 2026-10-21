
import os
from pathlib import Path
from dotenv import load_dotenv
from tavily import TavilyClient

# The project root is the parent of the tests folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load the .env file from the project root.
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

api_key = os.getenv("TAVILY_API_KEY")

if not api_key:
    raise RuntimeError(
        f"TAVILY_API_KEY was not found. Checked: {ENV_FILE}"
    )

client = TavilyClient(api_key=api_key)

response = client.search(
    query="companies that sponsored student hackathons in India",
    max_results=5,
    search_depth="basic",
)

results = response.get("results", [])

print("Tavily search succeeded.")
print(f"Results returned: {len(results)}")

for index, result in enumerate(results, start=1):
    print(f"\n--- Result {index} ---")
    print("Title:", result.get("title", ""))
    print("URL:", result.get("url", ""))
    print("Content:", result.get("content", "")[:500])
