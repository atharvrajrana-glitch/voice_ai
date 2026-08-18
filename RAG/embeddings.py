import asyncio
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


def _embed_content(text: str):
    """Run Gemini's synchronous embedding SDK call in a worker thread."""
    return client.models.embed_content(
        model="gemini-embedding-001",
        contents=text
    )


async def create_embedding(text: str):
    response = await asyncio.to_thread(_embed_content, text)
    return response.embeddings[0].values
