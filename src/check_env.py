import os

from dotenv import load_dotenv

load_dotenv()

if "ANTHROPIC_API_KEY" in os.environ and os.environ["ANTHROPIC_API_KEY"]:
    print("API key loaded")
else:
    print("API key missing")
