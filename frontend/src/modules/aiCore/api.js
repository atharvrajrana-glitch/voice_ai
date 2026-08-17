
const AI_CORE_URL = "http://localhost:8080/api/ai-core";
const API_BASE_URL = "http://localhost:8080";

export async function askAICore(text, { documentMode = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  const sessionId = localStorage.getItem("medclear_session_id");
  if (sessionId) headers["X-Session-ID"] = sessionId;

  const response = await fetch(AI_CORE_URL, {
    method: "POST",
    headers,
    body: JSON.stringify({ text, document_mode: documentMode }),
  });

  if (!response.ok) {
    throw new Error(`AI core request failed: ${response.status}`);
  }

  return response.json();
}

export async function createSession(phone) {
  const response = await fetch(`${API_BASE_URL}/api/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone }),
  });
  if (!response.ok) throw new Error("Could not create a patient session.");
  const data = await response.json();
  localStorage.setItem("medclear_session_id", data.session_id);
  return data;
}

export async function signUpPatient({ name, phone, email }) {
  const response = await fetch(`${API_BASE_URL}/api/v1/sessions/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, phone, email: email || null }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || "Could not create your patient account.");
  }
  const data = await response.json();
  localStorage.setItem("medclear_session_id", data.session_id);
  return data;
}

export async function getCurrentSession() {
  const sessionId = localStorage.getItem("medclear_session_id");
  if (!sessionId) return null;

  const response = await fetch(`${API_BASE_URL}/api/v1/sessions/me`, {
    headers: { "X-Session-ID": sessionId },
  });

  if (!response.ok) {
    localStorage.removeItem("medclear_session_id");
    return null;
  }
  return response.json();
}

export async function closeSession() {
  const sessionId = localStorage.getItem("medclear_session_id");
  try {
    if (sessionId) {
      await fetch(`${API_BASE_URL}/api/v1/sessions/logout`, {
        method: "POST",
        headers: { "X-Session-ID": sessionId },
      });
    }
  } finally {
    localStorage.removeItem("medclear_session_id");
  }
}
