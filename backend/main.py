from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel
from ai_core.service import get_ai_response

app = FastAPI()

origins = [
    "http://127.0.0.1:5174",
    "http://localhost:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    text: str

@app.get("/api/hello")
async def hello():
    return {"message": "Hello from FastAPI"}

@app.post("/api/ai-core")
def ai_core_endpoint(req: QueryRequest):
    return get_ai_response(req.text)