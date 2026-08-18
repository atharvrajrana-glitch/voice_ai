import React, { useState } from "react";
import { Home, Mic } from "lucide-react";
import VoiceModule from "./modules/voice/VoiceModule";
import HomePage from "./modules/home/HomePage";
import SessionManager from "./modules/session/SessionManager";

// App.jsx's only job is arranging modules — it never contains a
// module's actual logic. Add future modules (appointments, escalation)
// here the same way: import, add a tab, done.
export default function App() {
  const [page, setPage] = useState("home");

  const navButtonStyle = (active) => ({
    width: "100%", display: "flex", alignItems: "center", gap: "10px", padding: "12px 14px", border: "none", borderRadius: "10px",
    background: active ? "#DDEDE8" : "transparent", color: active ? "#1F6F64" : "#6B7A73", cursor: "pointer", font: "600 14px Inter, sans-serif", textAlign: "left",
  });

  return (
    <div style={{ background: "#F6F4EE", minHeight: "100vh" }}>
      <SessionManager>
      {(session) => (
      <div style={{ minHeight: "calc(100vh - 65px)", display: "flex" }}>
        <aside style={{ position: "sticky", top: "65px", alignSelf: "flex-start", width: "218px", height: "calc(100vh - 65px)", flexShrink: 0, padding: "24px 14px", overflowY: "auto", background: "#FFFFFF", borderRight: "1px solid #E9E4D8", boxSizing: "border-box" }}>
          <button type="button" onClick={() => setPage("home")} style={navButtonStyle(page === "home")}><Home size={18} /> Home</button>
          <button type="button" onClick={() => setPage("voice")} style={{ ...navButtonStyle(page === "voice"), marginTop: "4px" }}><Mic size={18} /> Voice Assistant</button>
        </aside>
        <div style={{ flex: 1, minWidth: 0 }}>{page === "home" ? <HomePage openVoiceAssistant={() => setPage("voice")} /> : <VoiceModule patientName={session.name} />}</div>
      </div>
      )}
      </SessionManager>
    </div>
  );
}
