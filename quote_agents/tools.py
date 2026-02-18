from langchain_google_genai import ChatGoogleGenerativeAI
import os

def get_llm():
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    return ChatGoogleGenerativeAI(model=model, temperature=0.2)
