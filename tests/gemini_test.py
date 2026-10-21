from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="Give me 5 reasons why a technology company might sponsor a college hackathon."
)

print(interaction.output_text)