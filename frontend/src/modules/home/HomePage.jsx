import React from "react";
import { FileUp, MessageCircleHeart, ShieldCheck, Stethoscope } from "lucide-react";

const steps = [
  { icon: FileUp, title: "Upload your report", text: "Use the + button in Voice Assistant to add a PDF report or bill securely." },
  { icon: MessageCircleHeart, title: "Ask by voice or text", text: "Ask what a result, medicine, charge, or instruction means in the way that feels easiest." },
  { icon: ShieldCheck, title: "Get clear, sourced answers", text: "MedClear searches only your uploaded document and identifies the supporting page." },
];

export default function HomePage({ openVoiceAssistant }) {
  return (
    <main style={{ width: "100%", maxWidth: "980px", margin: "0 auto", padding: "48px 32px", boxSizing: "border-box", fontFamily: "Inter, sans-serif" }}>
      <section style={{ background: "linear-gradient(135deg, #E5F0EC, #F8F6F0)", border: "1px solid #D9E5DE", borderRadius: "24px", padding: "clamp(30px, 6vw, 64px)", color: "#1F332C" }}>
        <div style={{ width: "48px", height: "48px", display: "grid", placeItems: "center", borderRadius: "14px", background: "#1F6F64", color: "#fff", marginBottom: "24px" }}><Stethoscope size={26} /></div>
        <p style={{ margin: 0, color: "#1F6F64", fontWeight: 700, fontSize: "12px", letterSpacing: ".1em", textTransform: "uppercase" }}>Your health documents, explained clearly</p>
        <h1 style={{ maxWidth: "650px", margin: "12px 0 16px", fontFamily: "Georgia, serif", fontSize: "clamp(34px, 5vw, 56px)", fontWeight: 500, lineHeight: 1.08 }}>Understand your medical documents in a simple conversation.</h1>
        <p style={{ maxWidth: "590px", margin: 0, color: "#52655E", fontSize: "17px", lineHeight: 1.6 }}>MedClear lets you upload a document and ask questions using your voice or keyboard. Answers are based on your own document, not general guesses.</p>
        <button type="button" onClick={openVoiceAssistant} style={{ marginTop: "28px", border: "none", borderRadius: "999px", padding: "14px 22px", background: "#1F6F64", color: "#fff", font: "600 15px Inter, sans-serif", cursor: "pointer" }}>Open Voice Assistant</button>
      </section>

      <section style={{ marginTop: "42px" }}>
        <p style={{ margin: 0, color: "#1F6F64", fontSize: "12px", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase" }}>How it works</p>
        <h2 style={{ margin: "10px 0 24px", color: "#1F332C", fontFamily: "Georgia, serif", fontSize: "30px", fontWeight: 500 }}>Three simple steps</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px" }}>
          {steps.map(({ icon: Icon, title, text }, index) => (
            <article key={title} style={{ padding: "24px", background: "#fff", border: "1px solid #E9E4D8", borderRadius: "16px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "18px" }}><span style={{ color: "#9A9384", fontSize: "13px", fontWeight: 700 }}>0{index + 1}</span><Icon size={24} color="#1F6F64" /></div>
              <h3 style={{ margin: "0 0 8px", color: "#1F332C", fontSize: "17px" }}>{title}</h3>
              <p style={{ margin: 0, color: "#6B7A73", fontSize: "14px", lineHeight: 1.55 }}>{text}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
