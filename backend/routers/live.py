import os
import asyncio
import base64
import logging
import time
from typing import Dict, Optional, List
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from ai_core.service import _validate_and_refresh_session
from ai_core.system_prompt import SYSTEM_PROMPT
from ai_core.tool_registry import ToolContext, execute_tool, get_groq_tools
from app.core.database import get_db

logger = logging.getLogger("live")
router = APIRouter()

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


# ---------------------------------------------------------------------------
# Long-lived session handle
# ---------------------------------------------------------------------------

class LiveSessionHandle:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.live_session = None
        self.browser_ws: Optional[WebSocket] = None
        self.turn_active = False
        self.turn_id = 0
        self.accumulated_user_transcript = ""
        self.frame_counters: Dict[int, int] = {}
        self.lock = asyncio.Lock()
        self._receive_task: Optional[asyncio.Task] = None
        self._closed = False
        self.created_at = time.time()

        # Conversation memory (no hardcoding)
        self.history: List[dict] = []          # [{"role": "user"|"model", "text": "..."}]
        self.max_history = 16
        self.current_intent: str = ""
        self.has_document = False  # ✅ Track if user uploaded a PDF
        self.resumption_token: str | None = None

        self.last_doctor_id: str | None = None
        self.last_doctor_name: str | None = None


    async def attach_browser(self, ws: WebSocket):
        async with self.lock:
            self.browser_ws = ws
            logger.critical(f"🔗 [SESSION {self.session_id}] Browser attached")

    async def detach_browser(self):
        async with self.lock:
            self.browser_ws = None
            logger.critical(f"🔓 [SESSION {self.session_id}] Browser detached")

    async def send_to_browser(self, data: dict):
        async with self.lock:
            if self.browser_ws is None:
                return
            try:
                await self.browser_ws.send_json(data)
            except Exception as e:
                logger.warning(f"Failed to send to browser: {e}")
                self.browser_ws = None

    def add_to_history(self, role: str, text: str):
        if not text or not text.strip():
            return
        cleaned = text.strip()
        self.history.append({"role": role, "text": cleaned})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        self._update_intent()

    def _update_intent(self):
        """Create a short running summary from recent history (no hardcoding)."""
        if not self.history:
            self.current_intent = ""
            return
        recent = self.history[-8:]
        parts = []
        for h in recent:
            role = "User" if h["role"] == "user" else "AI"
            parts.append(f"{role}: {h['text']}")
        self.current_intent = " | ".join(parts)

    def build_system_instruction(self) -> str:
        """
        Strong context injection without hardcoding any doctor names.
        """
        parts = [SYSTEM_PROMPT]

        if self.history:
            history_text = "\n".join(
                f"{'User' if h['role'] == 'user' else 'Assistant'}: {h['text']}"
                for h in self.history
            )

            parts.append(
                "\n\n### IMPORTANT - CONVERSATION CONTEXT\n"
                "You are continuing an ongoing conversation. "
                "The recent messages are below. "
                "You MUST remember and use all information already mentioned "
                "(doctor names, dates, times, symptoms, preferences, etc.). "
                "Do NOT ask again for information the user has already provided.\n\n"
                f"{history_text}\n\n"
                "Continue the conversation naturally from the last message. "
                "Never restart the conversation or forget previously mentioned details."
            )

        if self.current_intent:
            parts.append(
                f"\n### Current conversation summary:\n{self.current_intent}"
            )

        return "\n".join(parts)


_active_live_sessions: Dict[str, LiveSessionHandle] = {}
_registry_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Tools helper
# ---------------------------------------------------------------------------

def get_gemini_tools():
    try:
        groq_tools = get_groq_tools()
    except Exception as e:
        logger.warning(f"Could not load tools: {e}")
        return []

    function_declarations = []

    def clean_schema(schema):
        if not isinstance(schema, dict):
            return schema
        cleaned = {}
        for key, value in schema.items():
            if key == "type":
                if isinstance(value, list):
                    primary = next((t for t in value if t != "null"), "string")
                    cleaned["type"] = primary.upper() if isinstance(primary, str) else "STRING"
                elif isinstance(value, str):
                    cleaned["type"] = value.upper()
                else:
                    cleaned["type"] = "STRING"
            elif key == "properties" and isinstance(value, dict):
                cleaned["properties"] = {k: clean_schema(v) for k, v in value.items()}
            elif key == "items" and isinstance(value, dict):
                cleaned["items"] = clean_schema(value)
            else:
                cleaned[key] = value
        return cleaned

    for tool in groq_tools:
        if isinstance(tool, dict) and tool.get("type") == "function":
            func = tool.get("function", {})
            name = func.get("name")
            if not name:
                continue
            parameters = func.get("parameters", {"type": "object", "properties": {}})
            function_declarations.append({
                "name": name,
                "description": func.get("description", ""),
                "parameters": clean_schema(parameters),
            })

    return [{"function_declarations": function_declarations}] if function_declarations else []


# ---------------------------------------------------------------------------
# Create Live connection (with history injected)
# ---------------------------------------------------------------------------

async def _create_live_session(handle: LiveSessionHandle):
    model = "gemini-3.1-flash-live-preview"

    config_kwargs = {
        "response_modalities": ["AUDIO"],
        "system_instruction": handle.build_system_instruction(),
        "tools": get_gemini_tools(),
        "input_audio_transcription": types.AudioTranscriptionConfig(),
        "output_audio_transcription": types.AudioTranscriptionConfig(),
        "realtime_input_config": types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        ),
    }

    # Session Resumption
    if handle.resumption_token:
        config_kwargs["session_resumption"] = types.SessionResumptionConfig(
            handle=handle.resumption_token
        )
        logger.critical(
            f"♻️  Reconnecting with resumption token: {str(handle.resumption_token)[:40]}..."
        )

    config = types.LiveConnectConfig(**config_kwargs)

    cm = client.aio.live.connect(model=model, config=config)
    live_session = await cm.__aenter__()
    live_session._cm = cm
    return live_session


# ---------------------------------------------------------------------------
# Resilient receive loop (auto-reconnects + keeps history)
# ---------------------------------------------------------------------------

async def _gemini_receive_loop(handle: LiveSessionHandle, db: AsyncSession, db_session):
    logger.critical(f" [SESSION {handle.session_id}] Receive loop STARTED")

    current_ai_transcript = ""

    while not handle._closed:
        try:
            if handle.live_session is None:
                logger.critical(
                    f"🔄 [SESSION {handle.session_id}] Creating/Re-creating Live connection "
                    f"(history turns: {len(handle.history)})..."
                )
                handle.live_session = await _create_live_session(handle)
                await handle.send_to_browser({"type": "live_reconnected"})

            async for response in handle.live_session.receive():
                sc = response.server_content
                ts = time.time() - handle.created_at

                                # Capture resumption token (safe version)
                                # Safe resumption token capture (will not crash)
                if response.session_resumption_update:
                    try:
                        update = response.session_resumption_update
                        new_token = None

                        # Try common attribute names safely
                        for attr_name in ("token", "resumption_token", "handle", "session_handle", "id"):
                            if hasattr(update, attr_name):
                                val = getattr(update, attr_name)
                                if val:
                                    new_token = val
                                    break

                        if new_token:
                            handle.resumption_token = new_token
                            logger.critical(f"Saved resumption token: {str(new_token)[:50]}...")
                        else:
                            logger.debug(f"Resumption update received but no token found: {type(update)}")
                    except Exception as e:
                        logger.warning(f" Failed to extract resumption token: {e}")

                if sc and sc.turn_complete:
                    handle.turn_active = False
                    logger.critical(f" [TURN {handle.turn_id}@{ts:.1f}s] TURN_COMPLETE")

                    if current_ai_transcript.strip():
                        handle.add_to_history("model", current_ai_transcript)
                        current_ai_transcript = ""

                    await handle.send_to_browser({"type": "turn_complete"})

                if sc and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_b64 = base64.b64encode(part.inline_data.data).decode("utf-8")
                            await handle.send_to_browser({"type": "audio", "data": audio_b64})

                if sc and sc.input_transcription and sc.input_transcription.text:
                    handle.accumulated_user_transcript = sc.input_transcription.text
                    logger.critical(
                        f" [TURN {handle.turn_id}@{ts:.1f}s] User transcript: "
                        f"{handle.accumulated_user_transcript}"
                    )
                    await handle.send_to_browser({
                        "type": "user_transcript",
                        "text": handle.accumulated_user_transcript,
                    })

                if sc and sc.output_transcription and sc.output_transcription.text:
                    current_ai_transcript += sc.output_transcription.text
                    logger.critical(
                        f"[TURN {handle.turn_id}@{ts:.1f}s] AI transcript: "
                        f"{sc.output_transcription.text}"
                    )
                    await handle.send_to_browser({
                        "type": "ai_transcript",
                        "text": sc.output_transcription.text,
                    })
                # Tool calling with doctor_id protection
                if response.tool_call:
                    logger.critical(f" [TURN {handle.turn_id}@{ts:.1f}s] Tool call")
                    function_responses = []
                    context = ToolContext(
                        db=db,
                        session_id=db_session.id,
                        patient_id=db_session.patient_id,
                        user_text=handle.accumulated_user_transcript,
                    )

                    for fc in response.tool_call.function_calls:
                        args = dict(fc.args or {})

                        # Fix bad/missing doctor_id
                        if fc.name == "manage_appointment" and handle.last_doctor_id:
                            action = args.get("action")
                            if action in ("check", "book"):
                                incoming_id = str(args.get("doctor_id") or "")
                                if incoming_id != handle.last_doctor_id:
                                    logger.warning(
                                        f"model sent different doctor_id'{incoming_id}'"
                                        f" forcing last known {handle.last_doctor_id}"
                                    )
                                    args["doctor_id"] = handle.last_doctor_id
                        try:
                            result = await execute_tool(fc.name, args, context)
                        except Exception as e:
                            logger.error(f"Tool {fc.name} failed: {e}")
                            result = {"error": str(e)}

                        # Remember doctor from find_doctors
                        if (
                            fc.name == "find_doctors"
                            and result.get("ok")
                            and result.get("doctors")
                        ):
                            doctors = result["doctors"]
                            if len(doctors) == 1:
                                handle.last_doctor_id = doctors[0]["id"]
                                handle.last_doctor_name = doctors[0]["name"]
                                logger.critical(
                                    f"Remembered doctor: {handle.last_doctor_name} "
                                    f"({handle.last_doctor_id})"
                                )

                        function_responses.append(
                            types.FunctionResponse(
                                name=fc.name,
                                id=fc.id,
                                response={"result": result},
                            )
                        )

                    await handle.live_session.send_tool_response(
                        function_responses=function_responses
                    )

                if sc and sc.generation_complete:
                    logger.critical(f"🏁 [TURN {handle.turn_id}@{ts:.1f}s] Generation complete")

            logger.warning(
                f" [SESSION {handle.session_id}] Gemini closed the stream – "
                f"will reconnect with history"
            )

        except Exception as e:
            logger.error(
                f"❌ [SESSION {handle.session_id}] Receive error: "
                f"{type(e).__name__}: {e}"
            )

        # Clean up dead connection
        if handle.live_session is not None:
            try:
                await handle.live_session.__aexit__(None, None, None)
            except Exception:
                pass
            handle.live_session = None

        if handle._closed:
            break

        await asyncio.sleep(0.6)

    logger.critical(f" [SESSION {handle.session_id}] Receive loop permanently stopped")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/live")
async def live_endpoint(
    websocket: WebSocket,
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    await websocket.accept()
    logger.critical(f"🟢 [SESSION] Browser WebSocket ACCEPTED - session_id={session_id}")

    try:
        db_session = await _validate_and_refresh_session(UUID(session_id), db)
        if not db_session:
            await websocket.close(code=4001, reason="Invalid or expired session")
            return
    except Exception as e:
        logger.error(f"❌ [SESSION] Validation failed: {e}")
        await websocket.close(code=4001, reason="Invalid session")
        return

    handle: Optional[LiveSessionHandle] = None

    async with _registry_lock:
        existing = _active_live_sessions.get(session_id)

        if existing and not existing._closed:
            handle = existing
            logger.critical(f"♻️  [SESSION {session_id}] Re-attaching to existing handle")
            await handle.attach_browser(websocket)
        else:
            logger.critical(f"🆕 [SESSION {session_id}] Creating new long-lived handle")
            handle = LiveSessionHandle(session_id)
            await handle.attach_browser(websocket)
            _active_live_sessions[session_id] = handle

            handle._receive_task = asyncio.create_task(
                _gemini_receive_loop(handle, db, db_session)
            )

    # ---------- Browser → Gemini ----------
    try:
        while True:
            try:
                msg = await websocket.receive_json()
                msg_type = msg.get("type")
                ts = time.time() - handle.created_at

                # Wait until Live connection is ready
                if handle.live_session is None:
                    for _ in range(30):
                        await asyncio.sleep(0.1)
                        if handle.live_session is not None:
                            break
                    if handle.live_session is None:
                        logger.error("Live session not ready – dropping message")
                        continue

                if msg_type == "start_turn":
                    handle.turn_id += 1
                    handle.turn_active = True
                    handle.accumulated_user_transcript = ""
                    handle.frame_counters[handle.turn_id] = 0
                    logger.critical(f"[TURN {handle.turn_id}@{ts:.1f}s] START")
                    await handle.live_session.send_realtime_input(
                        activity_start=types.ActivityStart()
                    )

                elif msg_type == "audio":
                    if not handle.turn_active:
                        continue
                    handle.frame_counters[handle.turn_id] = (
                        handle.frame_counters.get(handle.turn_id, 0) + 1
                    )
                    if handle.frame_counters[handle.turn_id] == 1:
                        logger.critical(
                            f"🎙️ [TURN {handle.turn_id}@{ts:.1f}s] FIRST audio frame"
                        )
                    pcm = base64.b64decode(msg["data"])
                    await handle.live_session.send_realtime_input(
                        audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
                    )

                elif msg_type == "stop_turn":
                    if handle.turn_active:
                        total = handle.frame_counters.get(handle.turn_id, 0)
                        logger.critical(
                            f"[TURN {handle.turn_id}@{ts:.1f}s] STOP — {total} frames"
                        )
                        try:
                            await handle.live_session.send_realtime_input(
                                activity_end=types.ActivityEnd()
                            )
                            handle.turn_active = False

                            # Save user message to history
                            if handle.accumulated_user_transcript:
                                handle.add_to_history(
                                    "user", handle.accumulated_user_transcript
                                )

                            logger.critical(
                                f"[TURN {handle.turn_id}@{ts:.1f}s] activity_end CONFIRMED"
                            )
                        except Exception as e:
                            logger.error(f"activity_end failed: {e}")

                elif msg_type == "text":
                    handle.turn_id += 1
                    handle.turn_active = True
                    text = msg.get("text", "")
                    handle.accumulated_user_transcript = text
                    handle.add_to_history("user", text)
                    logger.critical(f"[TURN {handle.turn_id}@{ts:.1f}s] TEXT: {text}")
                    await handle.live_session.send(input=text, end_of_turn=True)

            except WebSocketDisconnect:
                logger.critical(
                    f"[SESSION {session_id}] Browser disconnected – "
                    f"Live session stays alive"
                )
                break
            except Exception as e:
                logger.error(f"Browser loop error: {type(e).__name__}: {e}")
                break

    finally:
        await handle.detach_browser()