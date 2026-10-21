
import json
import sys
from pathlib import Path

# Allow this test file to import modules from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import get_event_by_id
from sponsor_planner import generate_sponsor_plan


def main():
    event_id = int(input("Enter the saved event ID: "))
    user_id = int(input("Enter the user ID: "))

    print("\nLoading event from MySQL...")

    event = get_event_by_id(event_id, user_id)

    if event is None:
        print("Event not found for this user.")
        return

    print(f"Event loaded: {event['event_name']}")
    print("Generating sponsor categories and search queries...\n")

    plan = generate_sponsor_plan(event)

    print(json.dumps(plan, indent=2, ensure_ascii=False))

    # Save the generated plan locally for inspection.
    output_file = PROJECT_ROOT / "sponsor_plan_test.json"

    output_file.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nPlan saved to: {output_file}")


if __name__ == "__main__":
    main()
