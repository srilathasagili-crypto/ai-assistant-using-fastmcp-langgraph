from langchain_google_genai import ChatGoogleGenerativeAI
from graph.config import GEMINI_API_KEY


def get_llm(temperature: float = 0.3) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-3.6-flash",
        google_api_key=GEMINI_API_KEY,
        temperature=temperature,
        max_retries=2,
    )
