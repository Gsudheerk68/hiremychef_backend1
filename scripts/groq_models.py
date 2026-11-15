"""python -m scripts.groq_models   (lists model ids your Groq account can use)"""
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
key = os.environ.get("GROQ_API_KEY")
if not key:
    raise SystemExit("GROQ_API_KEY is not set in .env")

for m in sorted(Groq(api_key=key).models.list().data, key=lambda m: m.id):
    print(m.id)
