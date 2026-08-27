import React, { useState } from "react";
import { Home, Mic, Activity } from "lucide-react";
import Navbar from "./components/Navbar";
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
    background: active ? "rgba(124, 58, 237, 0.15)" : "transparent", color: active ? "#A78BFA" : "#8B7D9E", cursor: "pointer", font: "600 14px Inter, sans-serif", textAlign: "left", transition: "all 0.3s ease",
  });

  return (
    <div style={{ background: "#0F0D15", minHeight: "100vh" }}>
      <SessionManager>
      {(session, handleSignOut) => (
        <>
          <Navbar patientName={session.name} onSignOut={handleSignOut} />
          <div style={{ paddingTop: "92px", minHeight: "100vh", display: "flex" }}>
            <aside style={{ position: "sticky", top: "92px", alignSelf: "flex-start", width: "240px", height: "calc(100vh - 92px)", flexShrink: 0, padding: "24px 16px", overflowY: "auto", background: "rgba(26, 22, 34, 0.4)", borderRight: "1px solid rgba(124, 58, 237, 0.1)", boxSizing: "border-box" }}>
              {/* Navigation Buttons */}
              <div style={{ marginBottom: "24px" }}>
                <button type="button" onClick={() => setPage("home")} style={navButtonStyle(page === "home")}><Home size={18} /> Home</button>
                <button type="button" onClick={() => setPage("voice")} style={{ ...navButtonStyle(page === "voice"), marginTop: "8px" }}><Mic size={18} /> Voice Assistant</button>
              </div>

              {/* System Status Card */}
              <div style={{
                padding: "16px",
                borderRadius: "14px",
                background: "linear-gradient(135deg, rgba(124, 58, 237, 0.1), rgba(167, 139, 250, 0.05))",
                border: "1px solid rgba(124, 58, 237, 0.2)",
                marginTop: "16px",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
                  <div style={{
                    width: "10px",
                    height: "10px",
                    borderRadius: "50%",
                    background: "#10B981",
                    boxShadow: "0 0 8px rgba(16, 185, 129, 0.6)",
                  }} />
                  <span style={{ color: "#10B981", fontSize: "12px", fontWeight: "600" }}>System Online</span>
                </div>
                <div style={{ fontSize: "12px", color: "#9D8FB3", lineHeight: "1.5" }}>
                  <div style={{ marginBottom: "8px", display: "flex", alignItems: "center", gap: "6px" }}>
                    <Activity size={14} color="#A78BFA" />
                    <span>All systems operational</span>
                  </div>
                  <div style={{ padding: "8px", borderRadius: "8px", background: "rgba(26, 22, 34, 0.5)", fontSize: "11px", color: "#8B7D9E" }}>
                    ✓ Voice processing active<br/>
                    ✓ Database connected<br/>
                    ✓ AI services ready
                  </div>
                </div>
              </div>

              {/* Session Info */}
              <div style={{
                marginTop: "16px",
                padding: "12px",
                borderRadius: "12px",
                background: "rgba(124, 58, 237, 0.08)",
                border: "1px solid rgba(124, 58, 237, 0.15)",
                fontSize: "11px",
                color: "#8B7D9E",
              }}>
                <div style={{ color: "#A78BFA", fontWeight: "600", marginBottom: "4px" }}>Session Active</div>
                <div>Session expires after 1 hour of inactivity</div>
              </div>
            </aside>
            <div style={{ flex: 1, minWidth: 0 }}>{page === "home" ? <HomePage openVoiceAssistant={() => setPage("voice")} /> : <VoiceModule patientName={session.name} />}</div>
          </div>
        </>
      )}
      </SessionManager>
    </div>
  );
}
