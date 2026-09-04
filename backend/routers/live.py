import os
import asyncio
import base64
import logging
import time
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


@router.websocket("/ws/live")
async def live_endpoint(
    websocket: WebSocket,
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    await websocket.accept()
    logger.critical(f"🟢 [SESSION] Browser WebSocket ACCEPTED - session_id={session_id}")

    try:
        session = await _validate_and_refresh_session(UUID(session_id), db)
        if not session:
            await websocket.close(code=4001, reason="Invalid or expired session")
            return
    except Exception as e:
        logger.error(f"❌ [SESSION] Validation failed: {e}")
        await websocket.close(code=4001, reason="Invalid session")
        return

    # Manual turn control: WE decide when a turn starts/ends (button press/release),
    # not Gemini's own silence detection. This removes the entire VAD-mismatch class of bugs.
    model = "gemini-3.1-flash-live-preview"  # Latest Gemini Live model with audio
    
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_PROMPT,
        tools=get_gemini_tools(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        ),
    )

    accumulated_user_transcript = ""

    try:
        async with client.aio.live.connect(model=model, config=config) as live_session:
            logger.critical("✅ [SESSION] Gemini Live session CREATED")

            turn_id = 0
            frame_counters = {}
            session_start = time.time()
            # Only one flag needed: are we mid-turn (recording or awaiting response)?
            turn_active = False

            async def from_browser():
                nonlocal accumulated_user_transcript, turn_id, turn_active , frame_counters

                while True:
                    try:
                        msg = await websocket.receive_json()
                        msg_type = msg.get("type")
                        ts = time.time() - session_start

                        if msg_type == "start_turn":
                            turn_id += 1
                            turn_active = True
                            accumulated_user_transcript = ""
                            logger.critical(f"[TURN {turn_id}@{ts:.1f}s] START (button pressed)")
                            await live_session.send_realtime_input(
                                activity_start=types.ActivityStart()
                            )

                        elif msg_type == "audio":
                            if not turn_active:
                                continue
                            if turn_id not in frame_counters:
                                frame_counters[turn_id] = 0
                            frame_counters[turn_id] += 1
                            if frame_counters[turn_id] == 1:
                                logger.critical(f"🎙️ [TURN {turn_id}@{ts:.1f}s] FIRST audio frame received from browser")
                            pcm = base64.b64decode(msg["data"])
                            await live_session.send_realtime_input(
                                audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
                            )

                        elif msg_type == "stop_turn":
                            if turn_active:
                                total_frames = frame_counters.get(turn_id, 0)
                                logger.critical(f"[TURN {turn_id}@{ts:.1f}s] STOP requested — {total_frames} audio frames were sent this turn — sending activity_end...")
                                try:
                                    await live_session.send_realtime_input(activity_end=types.ActivityEnd())
                                    logger.critical(f"[TURN {turn_id}@{ts:.1f}s] activity_end SEND CONFIRMED")
                                    turn_active = False  # ✅ FIX: Mark turn as complete
                                except Exception as e:
                                    logger.error(f"[TURN {turn_id}@{ts:.1f}s] activity_end SEND FAILED: {type(e).__name__}: {e}")
                            

                        elif msg_type == "text":
                            turn_id += 1
                            turn_active = True
                            accumulated_user_transcript = ""
                            logger.critical(f"[TURN {turn_id}@{ts:.1f}s] TEXT: '{msg['text']}'")
                            await live_session.send(input=msg["text"], end_of_turn=True)

                    except WebSocketDisconnect as disconnect:
                        logger.critical(
                            "[SESSION] Browser WebSocket DISCONNECTED "
                            f"(code={disconnect.code}, reason={disconnect.reason!r})"
                        )
                        break
                    except Exception as e:
                        logger.error(f"[TURN {turn_id}] Error in from_browser: {type(e).__name__}: {e}")
                        break

            async def from_gemini():
                nonlocal accumulated_user_transcript, turn_active
                last_event_time = time.time()
                async def heartbeat():
                    while True:
                        await asyncio.sleep(5)
                        idle_for = time.time() - last_event_time
                        if idle_for > 5:
                            logger.warning(f"⏳ [HEARTBEAT] No events from Gemini for {idle_for:.1f}s (turn_active={turn_active})")

                hb_task = asyncio.create_task(heartbeat())

                try:
                    async for response in live_session.receive():
                        last_event_time = time.time()
                        ts = time.time() - session_start
                        sc = response.server_content

                        matched_something = False

                        if sc and sc.turn_complete:
                            matched_something = True
                            turn_active = False
                            logger.critical(f"✅ [TURN {turn_id}@{ts:.1f}s] TURN_COMPLETE")
                            await websocket.send_json({"type": "turn_complete"})

                        if sc and sc.model_turn:
                            matched_something = True
                            logger.critical(f"🔊 [TURN {turn_id}@{ts:.1f}s] MODEL_TURN with {len(sc.model_turn.parts)} parts")
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    audio_b64 = base64.b64encode(part.inline_data.data).decode("utf-8")
                                    logger.critical(f"🔊 [TURN {turn_id}@{ts:.1f}s] Sending audio chunk ({len(part.inline_data.data)} bytes) to frontend")
                                    await websocket.send_json({"type": "audio", "data": audio_b64})

                        if sc:
                            if sc.input_transcription and sc.input_transcription.text:
                                matched_something = True
                                accumulated_user_transcript = sc.input_transcription.text
                                logger.critical(f"📢 [TURN {turn_id}@{ts:.1f}s] User transcript: {accumulated_user_transcript}")
                                await websocket.send_json({
                                    "type": "user_transcript",
                                    "text": accumulated_user_transcript
                                })
                            if sc.output_transcription and sc.output_transcription.text:
                                matched_something = True
                                logger.critical(f"🎤 [TURN {turn_id}@{ts:.1f}s] AI transcript: {sc.output_transcription.text}")
                                await websocket.send_json({
                                    "type": "ai_transcript",
                                    "text": sc.output_transcription.text
                                })

                        if response.tool_call:
                            matched_something = True
                            logger.critical(f"🔧 [TURN {turn_id}@{ts:.1f}s] Tool call: {len(response.tool_call.function_calls)}")
                            function_responses = []
                            context = ToolContext(
                                db=db,
                                session_id=session.id,
                                patient_id=session.patient_id,
                                user_text=accumulated_user_transcript,
                            )
                            for fc in response.tool_call.function_calls:
                                try:
                                    result = await execute_tool(fc.name, fc.args or {}, context)
                                except Exception as e:
                                    logger.error(f"🔧 Tool {fc.name} failed: {e}")
                                    result = {"error": str(e)}
                                function_responses.append(
                                    types.FunctionResponse(name=fc.name, id=fc.id, response={"result": result})
                                )
                            await live_session.send_tool_response(function_responses=function_responses)
                        
                        # Log metadata responses for debugging
                        if response.voice_activity:
                            matched_something = True
                            logger.debug(f"🎙️ [TURN {turn_id}@{ts:.1f}s] Voice activity: {response.voice_activity.voice_activity_type}")
                        
                        if response.session_resumption_update:
                            matched_something = True
                            logger.debug(f"📋 [TURN {turn_id}@{ts:.1f}s] Session resumption update")
                        
                        if sc and sc.generation_complete:
                            matched_something = True
                            logger.critical(f"🏁 [TURN {turn_id}@{ts:.1f}s] Generation complete")
                        
                        if not matched_something:
                            logger.warning(f"⚠️ [TURN {turn_id}@{ts:.1f}s] UNHANDLED response type: {type(response)}")

                except Exception as e:
                    logger.critical(f"❌ [SESSION] Exception in from_gemini: {type(e).__name__}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                finally:
                    hb_task.cancel()
                    # `receive()` can finish without raising when Gemini closes
                    # its upstream Live stream. Do not keep accepting browser
                    # audio for that dead session; closing the browser socket
                    # lets the frontend create a fresh Live connection.
                    logger.critical("[SESSION] Gemini receive loop ended; closing browser WebSocket")
                    try:
                        await websocket.close(code=1011, reason="Gemini Live stream ended")
                    except Exception:
                        pass

            try:
                await asyncio.gather(from_browser(), from_gemini())
            finally:
                logger.critical("[SESSION] Gemini Live session ENDED")
                # Do not leave the browser with an OPEN socket after the upstream
                # Gemini session has ended. The frontend will establish a new one.
                try:
                    await websocket.close(code=1011, reason="Gemini Live session ended")
                except Exception:
                    pass

    except WebSocketDisconnect:
        logger.critical("[SESSION] Client disconnected")
    except Exception as e:
        logger.critical(f"[SESSION] Session error: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            await websocket.close(code=1011, reason=str(e)[:120])
        except Exception:
            pass
