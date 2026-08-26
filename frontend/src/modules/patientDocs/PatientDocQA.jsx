import React, { useState, useRef } from "react";
import { FileText, Loader2, Upload, X, CheckCircle2, Send, MessageSquare, Lightbulb, AlertCircle } from "lucide-react";
import { uploadPatientDocument, askPatientDocument } from "./api";

// A random session_id, generated fresh each time the app loads. This
// is what keeps this patient's document isolated from every other
// patient's — every upload and every question is tagged with it.
function generateSessionId() {
  return crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function PatientDocQA() {
  const [sessionId] = useState(generateSessionId);
  const [file, setFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null); // null | "uploading" | "done" | "error"
  const [uploadMessage, setUploadMessage] = useState("");

  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState([]); // { question, reply, resolved, source }
  const [asking, setAsking] = useState(false);

  const fileInputRef = useRef(null);

  const handleFileSelect = async (e) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setUploadStatus("uploading");
    setUploadMessage("");
    try {
      const result = await uploadPatientDocument(selected, sessionId);
      setUploadStatus(result.success ? "done" : "error");
      setUploadMessage(result.message);
    } catch (err) {
      setUploadStatus("error");
      setUploadMessage("Couldn't reach the server. Is the backend running?");
    }
  };

  const clearFile = () => {
    setFile(null);
    setUploadStatus(null);
    setUploadMessage("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleAsk = async () => {
    if (!question.trim() || uploadStatus !== "done") return;
    const q = question.trim();
    setAsking(true);
    setQuestion("");
    try {
      const result = await askPatientDocument(q, sessionId);
      setHistory((h) => [...h, { question: q, ...result }]);
    } catch (err) {
      setHistory((h) => [
        ...h,
        { question: q, reply: "Couldn't reach the server. Is the backend running?", resolved: false, source: null },
      ]);
    } finally {
      setAsking(false);
    }
  };

  return (
    <div
      style={{
        fontFamily: "'Inter', sans-serif",
        background: "#F8F7F4",
        width: "100%",
        maxWidth: "560px",
        margin: "0 auto",
        padding: "32px 24px",
        boxSizing: "border-box",
        borderRadius: "16px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "18px" }}>
        <FileText size={20} color="#A78BFA" />
        <div style={{ fontFamily: "'Fraunces', serif", fontSize: "22px", fontWeight: 500, color: "#E4D5F5" }}>
          Ask about your document
        </div>
      </div>

      <p style={{ fontSize: "14px", color: "#9D8FB3", marginBottom: "16px", lineHeight: 1.5 }}>
        Upload your report or bill once, then ask as many questions about it as you like. Every answer shows exactly where it came from.
      </p>

      {/* Upload area */}
      {file ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "#1A1622",
            border: "1px solid #2A2335",
            borderRadius: "10px",
            padding: "12px 14px",
            marginBottom: "16px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "14px", color: "#E4D5F5" }}>
            {uploadStatus === "uploading" ? (
              <Loader2 size={16} color="#A78BFA" className="spin" />
            ) : uploadStatus === "done" ? (
              <CheckCircle2 size={16} color="#7C3AED" />
            ) : (
              <FileText size={16} color="#FF6B6B" />
            )}
            <div>
              <div>{file.name}</div>
              {uploadMessage && (
                <div style={{ fontSize: "12px", color: uploadStatus === "error" ? "#FF9999" : "#9D8FB3", marginTop: "2px" }}>
                  {uploadMessage}
                </div>
              )}
            </div>
          </div>
          <button onClick={clearFile} style={{ background: "transparent", border: "none", cursor: "pointer", color: "#9D8FB3" }} aria-label="Remove file">
            <X size={16} />
          </button>
        </div>
      ) : (
        <button
          onClick={() => fileInputRef.current?.click()}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px",
            background: "#1A1622",
            border: "2px dashed #3A2A5A",
            borderRadius: "10px",
            padding: "20px",
            marginBottom: "16px",
            color: "#9D8FB3",
            fontSize: "14px",
            fontFamily: "'Inter', sans-serif",
            cursor: "pointer",
          }}
        >
          <Upload size={16} /> Upload your PDF report
        </button>
      )}
      <input ref={fileInputRef} type="file" accept="application/pdf" onChange={handleFileSelect} style={{ display: "none" }} />

      <style>{`
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>

      {/* Q&A history */}
      {history.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "16px" }}>
          {history.map((h, i) => (
            <div key={i} style={{ background: "#1A1622", border: "1px solid #2A2335", borderRadius: "12px", padding: "16px 18px" }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: "10px", fontSize: "13px", fontWeight: 600, color: "#A78BFA", marginBottom: "8px" }}>
                <MessageSquare size={16} style={{ marginTop: "2px", flexShrink: 0 }} />
                <span>{h.question}</span>
              </div>
              <div style={{ fontSize: "14px", color: "#E4D5F5", lineHeight: 1.6, marginBottom: h.source ? "10px" : 0 }}>{h.reply}</div>
              {h.source && (
                <div
                  style={{
                    fontSize: "12px",
                    color: "#9D8FB3",
                    background: "#1F1729",
                    borderRadius: "8px",
                    padding: "10px 12px",
                    marginTop: "8px",
                    borderLeft: "3px solid #7C3AED",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 500, marginBottom: "4px" }}>
                    <Lightbulb size={14} />
                    Source: {h.source.document}, page {h.source.page}
                  </div>
                  <div style={{ fontStyle: "italic" }}>&ldquo;{h.source.evidence}&rdquo;</div>
                </div>
              )}
              {!h.resolved && !h.source && (
                <div style={{ fontSize: "12px", color: "#8B7D9E", display: "flex", alignItems: "center", gap: "6px", marginTop: "4px" }}>
                  <AlertCircle size={14} />
                  Not found in the uploaded document.
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Question input */}
      <div style={{ display: "flex", gap: "8px" }}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          placeholder={uploadStatus === "done" ? "Ask a question about your document..." : "Upload a document first"}
          disabled={uploadStatus !== "done" || asking}
          style={{
            flex: 1,
            padding: "12px 14px",
            fontSize: "14px",
            fontFamily: "'Inter', sans-serif",
            border: "1px solid #2A2335",
            borderRadius: "10px",
            background: uploadStatus === "done" ? "#1F1729" : "#151013",
            color: "#E4D5F5",
          }}
        />
        <button
          onClick={handleAsk}
          disabled={uploadStatus !== "done" || asking || !question.trim()}
          style={{
            background: uploadStatus === "done" && question.trim() && !asking ? "#7C3AED" : "#4A3A6A",
            color: "#E4D5F5",
            border: "none",
            borderRadius: "10px",
            padding: "0 18px",
            cursor: uploadStatus === "done" && question.trim() && !asking ? "pointer" : "default",
            display: "flex",
            alignItems: "center",
          }}
          aria-label="Ask"
        >
          {asking ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
        </button>
      </div>
    </div>
  );
}
