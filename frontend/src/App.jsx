import React, { useState } from "react";
import VoiceModule from "./modules/voice/VoiceModule";
import PatientDocQA from "./modules/patientDocs/PatientDocQA";

// App.jsx's only job is arranging modules — it never contains a
// module's actual logic. Add future modules (appointments, escalation)
// here the same way: import, add a tab, done.
export default function App() {
  const [tab, setTab] = useState("voice");

  const tabStyle = (isActive) => ({
    padding: "10px 18px",
    borderRadius: "999px",
    border: "none",
    fontFamily: "'Inter', sans-serif",
    fontSize: "13px",
    fontWeight: 500,
    cursor: "pointer",
    background: isActive ? "#1F6F64" : "transparent",
    color: isActive ? "#F6F4EE" : "#6B7A73",
  });

  return (
    <div style={{ background: "#F6F4EE", minHeight: "100vh", paddingTop: "24px" }}>
      <div style={{ display: "flex", justifyContent: "center", gap: "8px", marginBottom: "12px", flexWrap: "wrap" }}>
        <button style={tabStyle(tab === "voice")} onClick={() => setTab("voice")}>
          Voice Assistant
        </button>
        <button style={tabStyle(tab === "patientDocs")} onClick={() => setTab("patientDocs")}>
          Ask About My Document
        </button>
      </div>

      {tab === "voice" && <VoiceModule />}
      {tab === "patientDocs" && <PatientDocQA />}
    </div>
  );
}