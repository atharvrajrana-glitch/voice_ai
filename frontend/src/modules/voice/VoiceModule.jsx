import React, { useState, useRef, useEffect, useCallback } from "react";
import { Mic, RotateCcw, Plus, FileText, Loader2, X } from "lucide-react";
import { askAICore } from "../aiCore/api";
import { uploadPatientDocument } from "../patientDocs/api";

const FONT_LINK = "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap";

// Maps the "language" field our AI core returns (e.g. "Hindi") to a
// BCP-47 locale code the browser's speech synthesis understands.
// Falls back to English if we don't recognize what came back.
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

// Use the script in the reply as a reliable fallback if the model omits or
// mislabels its language field. Hindi is written in the Devanagari block.
function getReplyLocale(reply, languageName) {
  if (/[\u0900-\u097F]/.test(reply || "")) return "hi-IN";
  return toSpeechLocale(languageName);
}

export default function VoiceModule({ patientName = "" }) {
  const [phase, setPhase] = useState("idle"); // idle | greeting | listening | thinking | speaking | unsupported
  const [transcriptLog, setTranscriptLog] = useState([]);
  const [interim, setInterim] = useState("");
  const [textQuestion, setTextQuestion] = useState("");
  const [needsGreeting, setNeedsGreeting] = useState(true);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null); // null | uploading | done | error
  const [uploadMessage, setUploadMessage] = useState("");
  const recognitionRef = useRef(null);
  const keepAliveRef = useRef(null);
  const voicesRef = useRef([]);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const link = document.createElement("link");
    link.href = FONT_LINK;
    link.rel = "stylesheet";
    document.head.appendChild(link);

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || !window.speechSynthesis) {
      setPhase("unsupported");
    }

    // Voice list loads asynchronously and is often empty on the very
    // first call. Preload it now and keep it updated, so by the time
    // we need a Hindi (or other) voice, it's actually available.
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

  const speak = useCallback((text, who, onDone, locale) => {
    window.speechSynthesis.cancel();
    window.speechSynthesis.resume(); // works around Chrome silently stalling after a delay
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 0.98;
    utter.pitch = 1.0;
    utter.lang = locale || "en-US";

    // Setting .lang alone isn't reliable — explicitly find and set the
    // matching voice object, preferring an exact match, then falling
    // back to any voice for the same language family (e.g. "hi").
    const voices = voicesRef.current.length ? voicesRef.current : window.speechSynthesis.getVoices();
    const wantLang = (locale || "en-US").toLowerCase();
    const wantPrefix = wantLang.split("-")[0];
    const matchedVoice =
      voices.find((v) => v.lang.toLowerCase() === wantLang) ||
      voices.find((v) => v.lang.toLowerCase().startsWith(`${wantPrefix}-`));
    if (matchedVoice) utter.voice = matchedVoice;

    utter.onend = () => {
      clearInterval(keepAliveRef.current);
      onDone && onDone();
    };
    utter.onerror = () => {
      clearInterval(keepAliveRef.current);
      onDone && onDone();
    };
    setPhase("speaking");
    setTranscriptLog((log) => [...log, { who, text }]);
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
      setInterim(interimText);
      if (finalText.trim()) {
        setInterim("");
        setTranscriptLog((log) => [...log, { who: "patient", text: finalText.trim() }]);
        recognition.stop();
        handlePatientText(finalText.trim());
      }
    };

    recognition.onerror = () => setPhase("idle");
    recognitionRef.current = recognition;
    setPhase("listening");
    setInterim("");
    recognition.start();
  }, []);

  // This is the ONLY function that changed from Module 1.
  // It used to return a fixed placeholder message. Now it calls
  // Module 2's AI core and speaks back a real answer.
  const handlePatientText = useCallback(
    async (heardText) => {
      setPhase("thinking");
      try {
        const startListeningAfterSpeech = () => {
          if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
            window.setTimeout(startListeningAfterSpeech, 120);
            return;
          }
          if (streamedResolved === false) console.log("Marked unresolved — escalation module will handle this later.");
          startListening();
        };
        const { reply, resolved, language } = await askAICore(heardText, {
          documentMode: uploadStatus === "done",
        });
        const safeReply = reply && reply.trim()
          ? reply
          : "Sorry, I wasn't able to work out an answer to that. Could you try asking again?";
        const locale = getReplyLocale(safeReply, language);
        speak(safeReply, "ai", () => {
          if (resolved === false) {
            // Placeholder hook for Module 5 (escalation) — not built yet.
            console.log("Marked unresolved — escalation module will handle this later.");
          }
          startListening();
        }, locale);
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
    if (!sessionId) return;

    setUploadedFile(file);
    setUploadStatus("uploading");
    setUploadMessage("");

    try {
      const result = await uploadPatientDocument(file, sessionId);
      setUploadStatus(result.success ? "done" : "error");
      setUploadMessage(result.success ? "" : "Unable to process this PDF. Please try another file.");
    } catch (error) {
      setUploadStatus("error");
      setUploadMessage("Unable to upload this PDF. Please try again.");
    }
  };

  const clearDocument = () => {
    setUploadedFile(null);
    setUploadStatus(null);
    setUploadMessage("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const activityLabel = {
    idle: needsGreeting ? "Tap the microphone to begin" : "Ready when you are",
    greeting: "Starting conversation...",
    listening: interim ? `Listening: “${interim}”` : "Listening...",
    thinking: "Thinking...",
    speaking: "Speaking...",
  }[phase];

  const submitTextQuestion = (event) => {
    event.preventDefault();
    const question = textQuestion.trim();
    if (!question || phase === "thinking") return;
    stopAll();
    setTextQuestion("");
    setTranscriptLog((log) => [...log, { who: "patient", text: question }]);
    handlePatientText(question);
  };

  return (
    <div
      style={{
        fontFamily: "'Inter', sans-serif",
        background: "#F6F4EE",
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
      `}</style>

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

          <div style={{ width: "100%", maxWidth: "440px", background: "#FFFFFF", border: "1px solid #E9E4D8", borderRadius: "12px", padding: "18px 20px", minHeight: "140px" }}>
            <div style={{ fontSize: "12px", letterSpacing: "0.06em", textTransform: "uppercase", color: "#9A9384", marginBottom: "10px", fontWeight: 500 }}>
              Transcript
            </div>
            {transcriptLog.length === 0 ? (
              <div style={{ fontSize: "14px", color: "#B4AE9E" }}>Nothing yet — ask a question below or use the microphone.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
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
