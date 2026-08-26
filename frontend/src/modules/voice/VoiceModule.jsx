import React, { useState, useRef, useEffect, useCallback } from "react";
import { Mic, RotateCcw, Plus, FileText, Loader2, X } from "lucide-react";
import { askAICore } from "../aiCore/api";
import { uploadPatientDocument } from "../patientDocs/api";

const FONT_LINK = "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap";

function toSpeechLocale(languageName) {
  if (!languageName) return "en-US";
  const map = {
    english: "en-US",
    hindi: "hi-IN",
    spanish: "es-ES",
    french: "fr-FR",
    arabic: "ar-SA",
    bengali: "bn-IN",
    tamil: "ta-IN",
    telugu: "te-IN",
    marathi: "mr-IN",
    gujarati: "gu-IN",
    punjabi: "pa-IN",
    urdu: "ur-IN",
    mandarin: "zh-CN",
    chinese: "zh-CN",
    portuguese: "pt-BR",
    german: "de-DE",
    japanese: "ja-JP",
    russian: "ru-RU",
  };
  const key = languageName.toLowerCase().trim();
  for (const name in map) {
    if (key.includes(name)) return map[name];
  }
  return "en-US";
}


export default function VoiceModule({ patientName = "" }) {
  const [phase, setPhase] = useState("idle"); 
  const [transcriptLog, setTranscriptLog] = useState([]);
  const [interim, setInterim] = useState("");
  const [textQuestion, setTextQuestion] = useState("");
  const [needsGreeting, setNeedsGreeting] = useState(true);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null); 
  const [uploadMessage, setUploadMessage] = useState("");
  const [bookingNotification, setBookingNotification] = useState(null);
  const recognitionRef = useRef(null);
  const keepAliveRef = useRef(null);
  const voicesRef = useRef([]);
  const fileInputRef = useRef(null);
  const handlePatientTextRef = useRef(null);
  let fullSentence = "";
  let accumulatedTTSBuffer = "";
  let hasStartedSpeaking = false;
  let timeChunksSeen = 0;
  let timesSuppressed = false;

  useEffect(() => {
    const link = document.createElement("link");
    link.href = FONT_LINK;
    link.rel = "stylesheet";
    document.head.appendChild(link);

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || !window.speechSynthesis) {
      setPhase("unsupported");
    }

    const loadVoices = () => {
      voicesRef.current = window.speechSynthesis.getVoices();
    };
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      document.head.removeChild(link);
      if (recognitionRef.current) recognitionRef.current.abort();
      window.speechSynthesis?.cancel();
      clearInterval(keepAliveRef.current);
    };
  }, []);

  function toSpokenSummary(text) {
    // Detect a list of 3+ time values (e.g., "9:00, 9:30, 10:00, 10:30...")
    const timeListPattern = /(\d{1,2}:\d{2}(?:\s*,\s*\d{1,2}:\d{2}){2,})/;
    const match = text.match(timeListPattern);
    if (match) {
      return text.replace(match[0], "the times shown below");
    }
    return text;
  }

  const speak = useCallback((text, who, onDone, locale, skipLog = false) => {
    window.speechSynthesis.resume(); 
    
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1.30;
    utter.pitch = 1.0;
    utter.lang = locale || "en-US";

    const voices = voicesRef.current.length ? voicesRef.current : window.speechSynthesis.getVoices();
    const wantLang = (locale || "en-US").toLowerCase();
    const wantPrefix = wantLang.split("-")[0];
    const matchedVoice =
      voices.find((v) => v.lang.toLowerCase() === wantLang) ||
      voices.find((v) => v.lang.toLowerCase().startsWith(`${wantPrefix}-`));
    if (matchedVoice) utter.voice = matchedVoice;

    utter.onend = () => {
      clearInterval(keepAliveRef.current);
      stopBargeInListener();
      onDone && onDone();
    };
    utter.onerror = () => {
      clearInterval(keepAliveRef.current);
      stopBargeInListener();
      onDone && onDone();
    };

    setPhase("speaking");
    startBargeInListener();
    
    if (!skipLog) {
      setTranscriptLog((log) => [...log, { who, text }]);
    }
    
    window.speechSynthesis.speak(utter);
  }, []);

  const startListening = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += t;
        else interimText += t;
      }
      if (finalText.trim()) {
        finalHandled = true;
        setInterim("");
        setTranscriptLog((log) => [...log, { who: "patient", text: finalText.trim() }]);
        recognition.stop();
        handlePatientTextRef.current(finalText.trim());
      }
     };

    let finalHandled = false;

    recognition.onerror = () => setPhase("idle");
    recognition.onend = () => {
      if (!finalHandled) {
        setInterim("");
        setPhase("idle");
      }
    };
    recognitionRef.current = recognition;
    setPhase("listening");
    setInterim("");
    recognition.start();
  }, []);

  const bargeInRecognitionRef = useRef(null);

const startBargeInListener = useCallback(() => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  const bargeRecognition = new SpeechRecognition();
  bargeRecognition.continuous = false;
  bargeRecognition.interimResults = true;
  bargeRecognition.lang = "en-US";

  let triggered = false;

  bargeRecognition.onresult = (event) => {
    let finalText = "";
    let interimText = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += t;
      else interimText += t;
    }

    // As soon as we detect ANY meaningful speech, interrupt immediately
    if (!triggered && (interimText.trim().length > 2 || finalText.trim())) {
      triggered = true;
      window.speechSynthesis.cancel();
      bargeRecognition.stop();

      if (finalText.trim()) {
        setInterim("");
        setTranscriptLog((log) => [...log, { who: "patient", text: finalText.trim() }]);
        handlePatientTextRef.current(finalText.trim());
      } else {
        // Got interim speech but not final yet — hand off to the normal listener
        // to capture the rest of what they're saying
        setPhase("listening");
        startListening();
      }
    }
  };

  bargeRecognition.onerror = () => {
    // Ignore — barge-in listener failing silently is fine, normal flow continues
  };

  bargeRecognition.onend = () => {
    // If it ended without triggering, that's normal (assistant finished speaking first)
  };

  bargeInRecognitionRef.current = bargeRecognition;
  try {
    bargeRecognition.start();
  } catch (e) {
    // Recognition may already be running elsewhere; ignore
  }
}, [startListening]);

const stopBargeInListener = useCallback(() => {
  if (bargeInRecognitionRef.current) {
    try {
      bargeInRecognitionRef.current.abort();
    } catch (e) {}
    bargeInRecognitionRef.current = null;
  }
}, []);

  const handlePatientText = useCallback(
    async (heardText) => {
      window.speechSynthesis.cancel();
      setPhase("thinking");
      
      let fullSentence = "";
      let accumulatedTTSBuffer = "";
      let hasStartedSpeaking = false;

      try {
        const startListeningAfterSpeech = () => {
          if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
            window.setTimeout(startListeningAfterSpeech, 120);
            return;
          }

          // --- NEW: Conversation End Detector ---
          // Checks if the AI included a farewell phrase in its final response
          const isClosingStatement = /(goodbye|have a (wonderful|great|good) day|bye\b|reach out if you need|take care|thank you|thanks for|appreciate|welcome)/i.test(fullSentence);
          
          if (isClosingStatement) {
             setPhase("idle");          // Power down the microphone
             setNeedsGreeting(true);    // Reset so the user can start a new session later
          } else {
             startListening();          // Keep the conversation going
          }
        };

        console.log("[Voice Debug] uploadStatus:", uploadStatus, "documentMode:", uploadStatus === "done");
        const { reply, resolved, language, isBookingSuccess } = await askAICore(
          heardText,
          { documentMode: uploadStatus === "done" },
          (newWord) => {
             fullSentence += newWord;
             
             setTranscriptLog((currentLog) => {
                const newLog = [...currentLog];
                const lastIndex = newLog.length - 1;
                const lastEntry = newLog[lastIndex];
                
                if (lastEntry && lastEntry.who === "ai") {
                    newLog[lastIndex] = { ...lastEntry, text: fullSentence };
                } else {
                    newLog.push({ who: "ai", text: fullSentence });
                }
                return newLog;
             });

             accumulatedTTSBuffer += newWord;
             
           if (/[.,!?]\s*$/.test(accumulatedTTSBuffer)) {
                const textToSpeak = accumulatedTTSBuffer.trim();
                accumulatedTTSBuffer = ""; 
                
                if (textToSpeak) {
                    // Detect if this chunk is primarily a time value (e.g., "09:00," or "10:30 or")
                    const isMostlyTime = /^(?:or|and)?\s*\d{1,2}:\d{2}\b[\s,.]*$/i.test(textToSpeak);

                    if (isMostlyTime) {
                        timeChunksSeen += 1;
                        if (timeChunksSeen <= 2) {
                            // Speak the first couple of times normally, so it doesn't feel abrupt
                            if (!hasStartedSpeaking) {
                                setPhase("speaking");
                                hasStartedSpeaking = true;
                            }
                            speak(textToSpeak, "ai", null, "en-US", true);
                        } else if (!timesSuppressed) {
                            // After a couple, announce once and go silent for the rest of the list
                            timesSuppressed = true;
                            speak("and more times shown below.", "ai", null, "en-US", true);
                        }
                        // else: silently skip — already announced
                    } else {
                        // Reset time-tracking once we're past the list (a real sentence chunk)
                        timeChunksSeen = 0;
                        timesSuppressed = false;
                        if (!hasStartedSpeaking) {
                            setPhase("speaking");
                            hasStartedSpeaking = true;
                        }
                        speak(textToSpeak, "ai", null, "en-US", true);
                    }
                }
            }
          }
        );

        // Show booking notification if appointment was booked
        if (isBookingSuccess) {
          // Extract doctor name (e.g., "Dr. Rajesh Sharma" or "DR. RAJESH SHARMA")
          const doctorMatch = fullSentence.match(/(?:Dr\.?\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/);
          const doctorName = doctorMatch ? doctorMatch[0] : "Your doctor";
          
          // Extract date (e.g., "August 28" or "August 28, 2026")
          const monthNames = "January|February|March|April|May|June|July|August|September|October|November|December";
          const dateMatch = fullSentence.match(new RegExp(`(${monthNames})\\s+(\\d{1,2})(?:,?\\s+(\\d{4}))?`));
          const dateStr = dateMatch ? `${dateMatch[1]} ${dateMatch[2]}${dateMatch[3] ? ", " + dateMatch[3] : ""}` : "";
          
          // Extract time (e.g., "9:00 AM" or "09:00" or "3:00 PM")
          const timeMatch = fullSentence.match(/(\d{1,2}):(\d{2})\s*(AM|PM|am|pm|a\.m|p\.m)?/i);
          let timeStr = "";
          if (timeMatch) {
            let hour = parseInt(timeMatch[1]);
            const minute = timeMatch[2];
            const period = (timeMatch[3] || "").toUpperCase().replace(".", "");
            
            // If no AM/PM provided, default to AM
            const displayPeriod = period ? period : "AM";
            timeStr = `${hour}:${minute} ${displayPeriod}`;
          }
          
          setBookingNotification({
            show: true,
            doctor: doctorName,
            date: dateStr || "Your appointment date",
            time: timeStr || "Your appointment time"
          });
          
          setTimeout(() => setBookingNotification(null), 5000);
        }

        if (accumulatedTTSBuffer.trim()) {
           speak(accumulatedTTSBuffer.trim(), "ai", () => {
               if (resolved === false) {
                 console.log("Marked unresolved — escalation module will handle this later.");
               }
               startListeningAfterSpeech();
           }, "en-US", true);
        } else {
            startListeningAfterSpeech();
        }

      } catch (err) {
        console.error("Unable to get an AI-core response:", err);
        speak(
          "I'm having trouble reaching the assistant right now. Please try again in a moment.",
          "ai",
          () => startListening()
        );
      }
   },
    [speak, startListening, uploadStatus]
  );

  useEffect(() => {
    handlePatientTextRef.current = handlePatientText;
  }, [handlePatientText]);

  const startGreeting = () => {
    const firstName = patientName.trim().split(/\s+/)[0];
    const greeting = firstName ? `Hello, ${firstName}. How can I help you?` : "Hello, how can I help you?";
    setNeedsGreeting(false);
    speak(greeting, "ai", startListening);
  };

  const stopAll = () => {
    window.speechSynthesis.cancel();
    recognitionRef.current?.abort();
    setPhase("idle");
    setInterim("");
  };

  const handleDocumentSelect = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const sessionId = localStorage.getItem("medclear_session_id");
    if (!sessionId) {
      console.error("[Voice Debug] No session ID found!");
      setUploadMessage("You must sign in first to upload documents");
      return;
    }

    setUploadedFile(file);
    setUploadStatus("uploading");
    setUploadMessage("");
    console.log("[Voice Debug] Starting upload for file:", file.name, "size:", file.size, "sessionId:", sessionId);

    try {
      const result = await uploadPatientDocument(file, sessionId);
      console.log("[Voice Debug] Upload API response:", JSON.stringify(result));
      
      if (!result) {
        console.error("[Voice Debug] Upload returned null/undefined");
        setUploadStatus("error");
        setUploadMessage("Upload failed - no response from server");
        return;
      }
      
      const success = result.success === true;  // Explicit true check
      console.log("[Voice Debug] Upload success:", success, "result.success:", result.success, "result.chunks_added:", result.chunks_added);
      
      if (success) {
        setUploadStatus("done");
        setUploadMessage("");
        console.log("[Voice Debug] ✓ Upload successful! Chunks added:", result.chunks_added);
      } else {
        setUploadStatus("error");
        setUploadMessage(result.message || "Unable to process this PDF. Please try another file.");
        console.error("[Voice Debug] Upload failed:", result.message);
      }
    } catch (error) {
      console.error("[Voice Debug] Upload exception:", error);
      setUploadStatus("error");
      setUploadMessage("Unable to upload this PDF. Please try again.");
    }
  };

  const clearDocument = () => {
    console.log("[Voice Debug] clearDocument called");
    setUploadedFile(null);
    setUploadStatus(null);
    setUploadMessage("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const activityLabel = {
    idle: needsGreeting ? "Tap the microphone to begin" : "Ready when you are",
    greeting: "Starting conversation...",
    listening: interim ? `Listening: "${interim}"` : "Listening...",
    thinking: "Thinking...",
    speaking: "Speaking...",
  }[phase];

  const submitTextQuestion = (event) => {
    event.preventDefault();
    const question = textQuestion.trim();
    if (!question || phase === "thinking") return;
    
    console.log("[Voice Debug] submitTextQuestion:", {
      question,
      uploadStatus,
      documentMode: uploadStatus === "done",
      phase
    });
    
    stopAll();
    setTextQuestion("");
    setTranscriptLog((log) => [...log, { who: "patient", text: question }]);
    handlePatientText(question);
  };

  return (
    <div
      style={{
        fontFamily: "'Inter', sans-serif",
        background: "#F8F7F4",
        minHeight: "600px",
        width: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "48px 24px 32px",
        boxSizing: "border-box",
        borderRadius: "16px",
      }}
    >
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes statusPulse { 0%, 100% { opacity: .45; transform: scale(.9); } 50% { opacity: 1; transform: scale(1); } }
        @keyframes slideIn { from { transform: translateX(400px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
      `}</style>

      {/* BOOKING NOTIFICATION */}
      {bookingNotification?.show && (
        <div style={{
          position: "fixed",
          top: "20px",
          right: "20px",
          background: "#1F6F64",
          color: "#FFFFFF",
          padding: "16px 24px",
          borderRadius: "8px",
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          zIndex: 1000,
          animation: "slideIn 0.3s ease-out",
          maxWidth: "300px"
        }}>
          <div style={{ fontSize: "16px", fontWeight: "600", marginBottom: "8px" }}>
            Appointment Confirmed
          </div>
          <div style={{ fontSize: "14px", opacity: 0.95, lineHeight: "1.5" }}>
            <div>{bookingNotification.doctor}</div>
            <div>{bookingNotification.date} at {bookingNotification.time}</div>
          </div>
        </div>
      )}

      <div style={{ width: "100%", maxWidth: "640px", textAlign: "center", margin: "4px 0 28px", padding: "25px 24px", boxSizing: "border-box", border: "1px solid #E7E2D7", borderRadius: "20px", background: "linear-gradient(135deg, #FCFBF7, #F1F5F0)" }}>
        <div style={{ marginBottom: "7px", color: "#1F6F64", fontSize: "11px", fontWeight: 700, letterSpacing: ".11em", textTransform: "uppercase" }}>MedClear</div>
        <div style={{ fontFamily: "'Fraunces', serif", fontSize: "clamp(28px, 4vw, 38px)", fontWeight: 500, color: "#18372E", lineHeight: 1.15 }}>
          Voice assistant
        </div>
        <div style={{ display: "inline-flex", alignItems: "center", gap: "8px", marginTop: "15px", padding: "7px 12px", borderRadius: "999px", background: "#FFFFFF", border: "1px solid #E4E9E3", color: "#557268", fontSize: "13px", fontWeight: 500 }}>
          <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: phase === "thinking" ? "#C08A36" : phase === "listening" ? "#1F6F64" : "#7E9D92", animation: phase === "idle" ? "none" : "statusPulse 1.2s ease-in-out infinite" }} />
          {activityLabel}
        </div>
      </div>

      {phase === "unsupported" && (
        <div style={{ marginTop: "48px", textAlign: "center", color: "#8A4B2E", maxWidth: "380px" }}>
          This browser doesn't support the Web Speech API. Try the latest Chrome or Edge.
        </div>
      )}

      {phase !== "unsupported" && (
        <>
          {transcriptLog.length > 0 && phase === "idle" && (
            <div style={{ width: "100%", maxWidth: "440px", display: "flex", justifyContent: "flex-end", marginBottom: "10px" }}>
              <button onClick={() => setTranscriptLog([])} style={{ background: "transparent", color: "#6B7A73", border: "1px solid #E4DCCC", borderRadius: "999px", padding: "12px 20px", fontSize: "14px", fontWeight: 500, fontFamily: "'Inter', sans-serif", cursor: "pointer", display: "flex", alignItems: "center", gap: "6px" }}>
                <RotateCcw size={14} /> Clear
              </button>
            </div>
          )}

          <div style={{ width: "100%", maxWidth: "440px", background: "#FFFFFF", border: "1px solid #E9E4D8", borderRadius: "12px", padding: "18px 20px", minHeight: "140px", maxHeight: "320px", display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: "12px", letterSpacing: "0.06em", textTransform: "uppercase", color: "#9A9384", marginBottom: "10px", fontWeight: 500 }}>
              Transcript
            </div>
            {transcriptLog.length === 0 ? (
              <div style={{ fontSize: "14px", color: "#B4AE9E" }}>Nothing yet — ask a question below or use the microphone.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", overflowY: "auto", overflowX: "hidden", flex: 1, paddingRight: "8px" }}>
                {transcriptLog.map((entry, i) => (
                  <div key={i} style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
                    <span style={{ fontSize: "11px", fontWeight: 600, color: entry.who === "ai" ? "#1F6F64" : "#8A6B3E", minWidth: "58px", marginTop: "2px" }}>
                      {entry.who === "ai" ? "ASSISTANT" : "PATIENT"}
                    </span>
                    <span style={{ fontSize: "14px", color: "#1F332C", lineHeight: 1.5 }}>{entry.text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ width: "100%", maxWidth: "640px", marginTop: "20px" }}>
            <input ref={fileInputRef} type="file" accept="application/pdf" onChange={handleDocumentSelect} style={{ display: "none" }} />
            {uploadedFile && (
              <div style={{ width: "min(250px, calc(100% - 24px))", display: "flex", alignItems: "center", gap: "13px", margin: "0 12px 10px", padding: "14px 16px", boxSizing: "border-box", background: "#3A3A3A", border: `1px solid ${uploadStatus === "error" ? "#9C5454" : "#565656"}`, borderRadius: "20px", color: "#F2F2F2" }}>
                <div style={{ width: "34px", height: "35px", display: "grid", placeItems: "center", color: "#FF4C4C", flexShrink: 0 }}>
                  {uploadStatus === "uploading" ? <Loader2 size={25} style={{ animation: "spin 1s linear infinite", color: "#D6D6D6" }} /> : <FileText size={30} strokeWidth={1.8} />}
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: "16px", fontWeight: 600 }}>{uploadedFile.name}</div>
                  <div style={{ marginTop: "3px", color: uploadStatus === "error" ? "#FF9999" : "#C6C6C6", fontSize: "14px" }}>{uploadStatus === "uploading" ? "Uploading..." : uploadStatus === "error" ? uploadMessage : "PDF"}</div>
                </div>
                <button type="button" onClick={clearDocument} aria-label="Remove document" style={{ alignSelf: "flex-start", padding: "1px", border: "none", background: "transparent", color: "#F2F2F2", cursor: "pointer", display: "flex" }}><X size={19} /></button>
              </div>
            )}
            <form onSubmit={submitTextQuestion} style={{ height: "68px", display: "flex", alignItems: "center", gap: "12px", padding: "0 10px 0 18px", boxSizing: "border-box", background: "#252525", border: "1px solid #383838", borderRadius: "34px", boxShadow: "0 5px 18px rgba(0, 0, 0, .14)" }}>
              <button type="button" onClick={() => fileInputRef.current?.click()} title="Upload a PDF document" aria-label="Upload a PDF document" style={{ width: "32px", height: "32px", display: "grid", placeItems: "center", padding: 0, border: "none", background: "transparent", color: "#D6D6D6", cursor: "pointer", flexShrink: 0 }}><Plus size={28} strokeWidth={1.7} /></button>
              <input value={textQuestion} onChange={(event) => setTextQuestion(event.target.value)} placeholder="Ask anything" aria-label="Ask MedClear" disabled={phase === "thinking"} style={{ flex: 1, minWidth: 0, border: "none", outline: "none", background: "transparent", color: "#F2F2F2", font: "400 19px Inter, sans-serif" }} />
              <button type="button" onClick={() => phase === "listening" ? stopAll() : needsGreeting ? startGreeting() : startListening()} disabled={phase === "thinking"} title={phase === "listening" ? "Stop listening" : needsGreeting ? "Start Voice Assistant" : "Speak your question"} aria-label={phase === "listening" ? "Stop listening" : needsGreeting ? "Start Voice Assistant" : "Speak your question"} style={{ width: "50px", height: "50px", display: "grid", placeItems: "center", padding: 0, border: "none", borderRadius: "50%", background: "#4B4B4B", color: "#F2F2F2", cursor: phase === "thinking" ? "wait" : "pointer", opacity: phase === "thinking" ? .5 : 1 }}><Mic size={26} strokeWidth={1.8} /></button>
            </form>
          </div>
        </>
      )}
    </div>
  );
}
