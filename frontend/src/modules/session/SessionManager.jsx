import React, { useEffect, useState } from "react";
import { LoaderCircle, LogOut, ShieldCheck, Stethoscope } from "lucide-react";
import { closeSession, createSession, getCurrentSession, signUpPatient } from "../aiCore/api";

const inputStyle = { width: "100%", padding: "13px 14px", border: "1px solid #3A2A5A", borderRadius: "9px", boxSizing: "border-box", font: "inherit", background: "#1F1729", color: "#E4D5F5" };
const labelStyle = { display: "block", marginBottom: "8px", color: "#E4D5F5", fontSize: "14px", fontWeight: 600 };

export default function SessionManager({ children }) {
  const [session, setSession] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [authMode, setAuthMode] = useState("signin");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getCurrentSession().then(setSession).finally(() => setCheckingSession(false));
  }, []);

  const submitAuth = async (event) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (authMode === "signup") {
        await signUpPatient({ name: name.trim(), phone: phone.trim(), email: email.trim() });
      } else {
        await createSession(phone.trim());
      }
      setSession(await getCurrentSession());
      setName("");
      setPhone("");
      setEmail("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const switchMode = (nextMode) => {
    setAuthMode(nextMode);
    setError("");
  };

  if (checkingSession) {
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#0F0D15", fontFamily: "Inter, sans-serif" }}>
        <style>{`@keyframes sessionSpin { to { transform: rotate(360deg); } }`}</style>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", color: "#7C3AED", fontSize: "18px", fontWeight: 500 }}>
          <LoaderCircle size={25} strokeWidth={2} style={{ animation: "sessionSpin .9s linear infinite" }} />
        </div>
      </main>
    );
  }

  if (!session) {
    const isSignUp = authMode === "signup";
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "24px", boxSizing: "border-box", background: "#0F0D15", fontFamily: "Inter, sans-serif" }}>
        <div style={{ width: "100%", maxWidth: "900px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0", borderRadius: "20px", overflow: "hidden", boxShadow: "0 20px 60px rgba(124, 58, 237, .15)" }}>
          {/* Left side - Hero */}
          <div style={{ background: "linear-gradient(135deg, #2A1B4D, #1A0F2E)", padding: "60px 40px", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "flex-start", color: "#E4D5F5" }}>
            <div style={{ width: "64px", height: "64px", display: "grid", placeItems: "center", borderRadius: "16px", background: "rgba(124, 58, 237, 0.2)", marginBottom: "32px" }}>
              <Stethoscope size={32} color="#A78BFA" />
            </div>
            <h2 style={{ fontFamily: "Georgia, serif", fontSize: "36px", fontWeight: 500, margin: "0 0 16px", color: "#E4D5F5", lineHeight: 1.2 }}>
              {isSignUp ? "Join MedClear" : "Welcome Back"}
            </h2>
            <p style={{ fontSize: "16px", color: "#C4B5FD", lineHeight: 1.6, margin: 0 }}>
              {isSignUp 
                ? "Secure access to your medical documents and AI-powered insights, available 24/7."
                : "Sign in to continue accessing your secure patient health assistant."
              }
            </p>
            <div style={{ marginTop: "48px", display: "flex", flexDirection: "column", gap: "16px" }}>
              {[
                { icon: "🔒", text: "End-to-end encrypted" },
                { icon: "⏱️", text: "Instant responses" },
                { icon: "📱", text: "Voice or text enabled" }
              ].map((item, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: "12px", fontSize: "14px", color: "#A78BFA" }}>
                  <span style={{ fontSize: "20px" }}>{item.icon}</span>
                  {item.text}
                </div>
              ))}
            </div>
          </div>

          {/* Right side - Form */}
          <div style={{ background: "#1A1622", padding: "60px 40px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <form onSubmit={submitAuth}>
              <p style={{ margin: "0 0 8px", color: "#A78BFA", fontSize: "12px", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase" }}>MedClear Authentication</p>
              <h1 style={{ margin: "0 0 24px", color: "#E4D5F5", fontFamily: "Georgia, serif", fontSize: "28px", fontWeight: 500 }}>
                {isSignUp ? "Create Account" : "Sign In"}
              </h1>

              {isSignUp && (
                <div style={{ marginBottom: "16px" }}>
                  <label htmlFor="name" style={labelStyle}>Full Name</label>
                  <input 
                    id="name" 
                    value={name} 
                    onChange={(event) => setName(event.target.value)} 
                    autoComplete="name" 
                    placeholder="Your full name" 
                    required 
                    disabled={submitting} 
                    style={{...inputStyle, placeholder: "#6B5B7F"}} 
                  />
                </div>
              )}

              <div style={{ marginBottom: "16px" }}>
                <label htmlFor="phone" style={labelStyle}>Phone Number</label>
                <input 
                  id="phone" 
                  value={phone} 
                  onChange={(event) => setPhone(event.target.value)} 
                  inputMode="tel" 
                  autoComplete="tel" 
                  placeholder="+91     " 
                  required 
                  disabled={submitting} 
                  style={inputStyle} 
                />
              </div>

              {isSignUp && (
                <div style={{ marginBottom: "24px" }}>
                  <label htmlFor="email" style={labelStyle}>Email <span style={{ color: "#9D8FB3", fontWeight: 400 }}>(optional)</span></label>
                  <input 
                    id="email" 
                    type="email" 
                    value={email} 
                    onChange={(event) => setEmail(event.target.value)} 
                    autoComplete="email" 
                    placeholder="name@example.com" 
                    disabled={submitting} 
                    style={inputStyle} 
                  />
                </div>
              )}

              {error && (
                <p role="alert" style={{ margin: "0 0 16px", color: "#FF9999", fontSize: "13px", padding: "10px 12px", background: "rgba(255, 68, 68, 0.1)", borderRadius: "8px", border: "1px solid #DC2626" }}>
                  {error}
                </p>
              )}

              <button 
                type="submit" 
                disabled={submitting} 
                style={{ 
                  width: "100%", 
                  marginBottom: "20px", 
                  padding: "14px", 
                  border: "none", 
                  borderRadius: "9px", 
                  background: "#7C3AED", 
                  color: "#fff", 
                  cursor: submitting ? "wait" : "pointer", 
                  font: "600 15px Inter, sans-serif", 
                  opacity: submitting ? 0.7 : 1,
                  transition: "all 0.2s"
                }}
              >
                {submitting ? (isSignUp ? "Creating account..." : "Signing in...") : (isSignUp ? "Create Account" : "Sign In")}
              </button>

              <div style={{ textAlign: "center" }}>
                <p style={{ margin: 0, color: "#9D8FB3", fontSize: "14px" }}>
                  {isSignUp ? "Already have an account? " : "Don't have an account? "}
                  <button 
                    type="button" 
                    onClick={() => switchMode(isSignUp ? "signin" : "signup")} 
                    style={{ 
                      padding: 0, 
                      border: "none", 
                      background: "none", 
                      color: "#A78BFA", 
                      cursor: "pointer", 
                      font: "600 14px Inter, sans-serif",
                      textDecoration: "underline"
                    }}
                  >
                    {isSignUp ? "Sign In" : "Create Account"}
                  </button>
                </p>
              </div>

              <div style={{ marginTop: "24px", paddingTop: "24px", borderTop: "1px solid #2A2335", display: "flex", alignItems: "center", gap: "8px", color: "#9D8FB3", fontSize: "12px" }}>
                <ShieldCheck size={16} color="#A78BFA" />
                <span>Your data is encrypted and secure</span>
              </div>
            </form>
          </div>
        </div>
      </main>
    );
  }

  const signOut = async () => {
    await closeSession();
    setSession(null);
  };

  return typeof children === "function" ? children(session, signOut) : children;
}
