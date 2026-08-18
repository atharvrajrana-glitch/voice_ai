import React, { useEffect, useState } from "react";
import { LoaderCircle, LogOut, ShieldCheck, Stethoscope } from "lucide-react";
import { closeSession, createSession, getCurrentSession, signUpPatient } from "../aiCore/api";

const inputStyle = { width: "100%", padding: "13px 14px", border: "1px solid #D4D2CC", borderRadius: "9px", boxSizing: "border-box", font: "inherit" };
const labelStyle = { display: "block", marginBottom: "8px", color: "#1F332C", fontSize: "14px", fontWeight: 600 };

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
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#F6F4EE", fontFamily: "Inter, sans-serif" }}>
        <style>{`@keyframes sessionSpin { to { transform: rotate(360deg); } }`}</style>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", color: "#1F6F64", fontSize: "18px", fontWeight: 500 }}>
          <LoaderCircle size={25} strokeWidth={2} style={{ animation: "sessionSpin .9s linear infinite" }} />
        </div>
      </main>
    );
  }

  if (!session) {
    const isSignUp = authMode === "signup";
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: "24px", boxSizing: "border-box", background: "#F6F4EE", fontFamily: "Inter, sans-serif" }}>
        <section style={{ width: "100%", maxWidth: "420px", padding: "40px", boxSizing: "border-box", background: "#fff", border: "1px solid #E9E4D8", borderRadius: "20px", boxShadow: "0 16px 42px rgba(31, 51, 44, .08)" }}>
          <div style={{ width: "48px", height: "48px", display: "grid", placeItems: "center", borderRadius: "14px", background: "#DDEDE8", color: "#1F6F64", marginBottom: "24px" }}><Stethoscope size={25} /></div>
          <p style={{ margin: 0, color: "#1F6F64", fontSize: "12px", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase" }}>MedClear</p>
          <h1 style={{ margin: "8px 0 10px", color: "#1F332C", fontFamily: "Georgia, serif", fontSize: "32px", fontWeight: 500 }}>{isSignUp ? "Create your account" : "Welcome back"}</h1>
          <p style={{ margin: "0 0 28px", color: "#6B7A73", lineHeight: 1.55 }}>{isSignUp ? "Register as a new patient and start your secure session." : "Sign in with your registered phone number to use your secure patient assistant."}</p>
          <form onSubmit={submitAuth}>
            {isSignUp && <div style={{ marginBottom: "16px" }}><label htmlFor="name" style={labelStyle}>Full name</label><input id="name" value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" placeholder="Enter your full name" required disabled={submitting} style={inputStyle} /></div>}
            <label htmlFor="phone" style={labelStyle}>Phone number</label>
            <input id="phone" value={phone} onChange={(event) => setPhone(event.target.value)} inputMode="tel" autoComplete="tel" placeholder="Enter your phone number" required disabled={submitting} style={inputStyle} />
            {isSignUp && <div style={{ marginTop: "16px" }}><label htmlFor="email" style={labelStyle}>Email <span style={{ color: "#6B7A73", fontWeight: 400 }}>(optional)</span></label><input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" placeholder="name@example.com" disabled={submitting} style={inputStyle} /></div>}
            {error && <p role="alert" style={{ margin: "10px 0 0", color: "#8A4B2E", fontSize: "13px" }}>{error}</p>}
            <button type="submit" disabled={submitting} style={{ width: "100%", marginTop: "20px", padding: "14px", border: "none", borderRadius: "9px", background: "#1F6F64", color: "#fff", cursor: submitting ? "wait" : "pointer", font: "600 15px Inter, sans-serif", opacity: submitting ? 0.7 : 1 }}>{submitting ? (isSignUp ? "Creating account..." : "Signing in...") : (isSignUp ? "Create account" : "Sign in securely")}</button>
          </form>
          <p style={{ margin: "18px 0 0", color: "#6B7A73", fontSize: "13px", textAlign: "center" }}>{isSignUp ? "Already registered? " : "New to MedClear? "}<button type="button" onClick={() => switchMode(isSignUp ? "signin" : "signup")} style={{ padding: 0, border: "none", background: "none", color: "#1F6F64", cursor: "pointer", font: "600 13px Inter, sans-serif" }}>{isSignUp ? "Sign in" : "Create an account"}</button></p>
          <p style={{ display: "flex", alignItems: "center", gap: "7px", margin: "24px 0 0", color: "#6B7A73", fontSize: "12px", lineHeight: 1.4 }}><ShieldCheck size={16} color="#1F6F64" /> Your session expires automatically after one hour.</p>
        </section>
      </main>
    );
  }

  const signOut = async () => {
    await closeSession();
    setSession(null);
  };

  return <><header style={{ position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "space-between", gap: "16px", minHeight: "65px", padding: "12px 28px", boxSizing: "border-box", background: "#fff", borderBottom: "1px solid #E9E4D8", fontFamily: "Inter, sans-serif" }}><span style={{ color: "#1F332C", fontFamily: "Georgia, serif", fontSize: "21px" }}>MedClear</span><button onClick={signOut} style={{ display: "flex", alignItems: "center", gap: "7px", border: "1px solid #D4D2CC", borderRadius: "8px", padding: "9px 12px", background: "#fff", color: "#8A4B2E", cursor: "pointer", font: "500 13px Inter, sans-serif" }}><LogOut size={16} /> Sign out</button></header>{typeof children === "function" ? children(session) : children}</>;
}
