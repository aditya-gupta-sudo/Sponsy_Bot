import json

companyi = {
    "company": "Google",
    "industry": "Technology",
    "sponsorship_amount": 100000,
    "possible_asks": ["Financial", "Cloud Credits", "Swag"],
    "previous_sponsor": True
}

json_data = json.dumps(companyi)

print(json_data)

data = json.loads(json_data)
print(f"Company: {data["company"]} \n Sponsorship Amount: {data["sponsorship_amount"]}")