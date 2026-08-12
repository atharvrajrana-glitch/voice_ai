# Voice AI React + FastAPI

## Setup

### Backend
1. Open a terminal in `backend`
2. Create a Python environment:
   - `python -m venv venv`
   - `venv\Scripts\activate`
3. Install dependencies:
   - `pip install -r requirements.txt`
4. Run the backend:
   - `uvicorn main:app --reload --host 127.0.0.1 --port 8000`

### Frontend
1. Open a terminal in `frontend`
2. Install dependencies:
   - `npm install`
3. Run the frontend:
   - `npm run dev`

## Usage
- Frontend: `http://localhost:5173`
- Backend: `http://127.0.0.1:8000`

## API
- `GET /api/hello` returns a JSON message
