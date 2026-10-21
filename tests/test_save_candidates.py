
import json
import sys
from pathlib import Path

# Locate the SponsyBot project root.
BASE_DIR = Path(__file__).resolve().parents[1]

# Add the project root to Python's module search path.
sys.path.insert(0, str(BASE_DIR))

from database import save_company_candidates

# Load the extracted candidates.
json_path = BASE_DIR / "company_candidates_test.json"

with json_path.open("r", encoding="utf-8") as file:
    data = json.load(file)

event_id = 6
candidates = data["candidates"]

print(f"Event: {data['event_name']}")
print(f"Candidates loaded: {len(candidates)}")

try:
    result = save_company_candidates(event_id, candidates)
    print("\nDatabase save completed:")
    print(json.dumps(result, indent=2))

except Exception as error:
    print(f"\nDatabase save failed: {error}")
    raise
