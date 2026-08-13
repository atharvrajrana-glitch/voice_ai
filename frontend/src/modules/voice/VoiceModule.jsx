import React, { useState, useRef, useEffect, useCallback } from "react";
import { Mic, MicOff, Volume2, RotateCcw } from "lucide-react";
import { askAICore } from "../aiCore/api";

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

export default function VoiceModule() {
  const [phase, setPhase] = useState("idle"); // idle | greeting | listening | thinking | speaking | unsupported
  const [transcriptLog, setTranscriptLog] = useState([]);
  const [interim, setInterim] = useState("");
  const recognitionRef = useRef(null);
  const keepAliveRef = useRef(null);
  const voicesRef = useRef([]);

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
        const { reply, resolved, language } = await askAICore(heardText);
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
        speak(
          "I'm having trouble reaching the assistant right now. Please try again in a moment.",
          "ai",
          () => startListening()
        );
      }
    },
    [speak, startListening]
  );

  const begin = () => {
    setPhase("greeting");
    setTranscriptLog([]);
    speak("Hello, how can I help you?", "ai", () => startListening());
  };

  const stopAll = () => {
    window.speechSynthesis.cancel();
    recognitionRef.current?.abort();
    setPhase("idle");
    setInterim("");
  };

  const orbState =
    phase === "listening" ? "listening" : phase === "speaking" || phase === "greeting" ? "speaking" : phase === "thinking" ? "thinking" : "idle";

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
        @keyframes breathe { 0%,100%{transform:scale(1);opacity:.9} 50%{transform:scale(1.06);opacity:1} }
        @keyframes ring1 { 0%{transform:scale(1);opacity:.5} 100%{transform:scale(1.8);opacity:0} }
        @keyframes ring2 { 0%{transform:scale(1);opacity:.35} 100%{transform:scale(2.2);opacity:0} }
        @keyframes speakPulse { 0%,100%{transform:scaleY(.4)} 50%{transform:scaleY(1)} }
        @keyframes thinkDot { 0%,80%,100%{opacity:.25} 40%{opacity:1} }
        @media (prefers-reduced-motion: reduce) { .orb,.ring,.bar,.dot { animation: none !important; } }
      `}</style>

      <div style={{ textAlign: "center", marginBottom: "8px" }}>
        <div style={{ fontSize: "13px", letterSpacing: "0.08em", textTransform: "uppercase", color: "#6B7A73", fontWeight: 500 }}>
          MedClear voice assistant
        </div>
        <div style={{ fontFamily: "'Fraunces', serif", fontSize: "26px", fontWeight: 500, color: "#1F332C", marginTop: "6px" }}>
          Voice AI core
        </div>
      </div>

      {phase === "unsupported" && (
        <div style={{ marginTop: "48px", textAlign: "center", color: "#8A4B2E", maxWidth: "380px" }}>
          This browser doesn't support the Web Speech API. Try the latest Chrome or Edge.
        </div>
      )}

      {phase !== "unsupported" && (
        <>
          <div style={{ position: "relative", width: "220px", height: "220px", display: "flex", alignItems: "center", justifyContent: "center", margin: "40px 0 28px" }}>
            {orbState === "listening" && (
              <>
                <span className="ring" style={{ position: "absolute", width: "180px", height: "180px", borderRadius: "50%", border: "1.5px solid #1F6F64", animation: "ring1 2s ease-out infinite" }} />
                <span className="ring" style={{ position: "absolute", width: "180px", height: "180px", borderRadius: "50%", border: "1.5px solid #1F6F64", animation: "ring2 2s ease-out infinite 0.5s" }} />
              </>
            )}
            <div
              className="orb"
              style={{
                width: "150px",
                height: "150px",
                borderRadius: "50%",
                background: orbState === "idle" ? "#E4E0D5" : "#1F6F64",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                animation: orbState !== "idle" ? "breathe 1.6s ease-in-out infinite" : "none",
                boxShadow: orbState !== "idle" ? "0 8px 24px rgba(31,111,100,0.25)" : "none",
                transition: "background 0.4s ease",
              }}
            >
              {orbState === "speaking" ? (
                <div style={{ display: "flex", gap: "5px", alignItems: "center", height: "36px" }}>
                  {[0, 1, 2, 3, 4].map((i) => (
                    <span key={i} className="bar" style={{ width: "5px", height: "100%", borderRadius: "3px", background: "#F6F4EE", animation: `speakPulse ${0.5 + i * 0.08}s ease-in-out infinite` }} />
                  ))}
                </div>
              ) : orbState === "listening" ? (
                <Mic size={40} color="#F6F4EE" strokeWidth={1.6} />
              ) : orbState === "thinking" ? (
                <div style={{ display: "flex", gap: "6px" }}>
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="dot" style={{ width: "9px", height: "9px", borderRadius: "50%", background: "#F6F4EE", animation: `thinkDot 1.2s ease-in-out infinite ${i * 0.2}s` }} />
                  ))}
                </div>
              ) : (
                <Mic size={40} color="#9A9384" strokeWidth={1.6} />
              )}
            </div>
          </div>

          <div style={{ minHeight: "24px", fontSize: "14px", color: "#6B7A73", marginBottom: "20px", textAlign: "center" }}>
            {phase === "idle" && "Tap to begin"}
            {phase === "greeting" && "Speaking..."}
            {phase === "listening" && (interim ? `"${interim}"` : "Listening...")}
            {phase === "thinking" && "Thinking..."}
            {phase === "speaking" && "Speaking..."}
          </div>

          <div style={{ display: "flex", gap: "12px", marginBottom: "28px" }}>
            {phase === "idle" ? (
              <button onClick={begin} style={{ background: "#1F6F64", color: "#F6F4EE", border: "none", borderRadius: "999px", padding: "14px 32px", fontSize: "15px", fontWeight: 500, fontFamily: "'Inter', sans-serif", cursor: "pointer", display: "flex", alignItems: "center", gap: "8px" }}>
                <Volume2 size={18} /> Tap to begin
              </button>
            ) : (
              <button onClick={stopAll} style={{ background: "#FFFFFF", color: "#8A4B2E", border: "1px solid #E4DCCC", borderRadius: "999px", padding: "12px 24px", fontSize: "14px", fontWeight: 500, fontFamily: "'Inter', sans-serif", cursor: "pointer", display: "flex", alignItems: "center", gap: "8px" }}>
                <MicOff size={16} /> Stop
              </button>
            )}
            {transcriptLog.length > 0 && phase === "idle" && (
              <button onClick={() => setTranscriptLog([])} style={{ background: "transparent", color: "#6B7A73", border: "1px solid #E4DCCC", borderRadius: "999px", padding: "12px 20px", fontSize: "14px", fontWeight: 500, fontFamily: "'Inter', sans-serif", cursor: "pointer", display: "flex", alignItems: "center", gap: "6px" }}>
                <RotateCcw size={14} /> Clear
              </button>
            )}
          </div>

          <div style={{ width: "100%", maxWidth: "440px", background: "#FFFFFF", border: "1px solid #E9E4D8", borderRadius: "12px", padding: "18px 20px", minHeight: "140px" }}>
            <div style={{ fontSize: "12px", letterSpacing: "0.06em", textTransform: "uppercase", color: "#9A9384", marginBottom: "10px", fontWeight: 500 }}>
              Transcript
            </div>
            {transcriptLog.length === 0 ? (
              <div style={{ fontSize: "14px", color: "#B4AE9E" }}>Nothing yet — tap begin and speak.</div>
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
        </>
      )}
    </div>
  );
}
