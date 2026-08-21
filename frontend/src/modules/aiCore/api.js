const AI_CORE_URL = `${import.meta.env.VITE_API_URL || "http://localhost:8080"}/api/ai-core`;
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8080";

export async function askAICore(text, { documentMode = false } = {}, onChunk) {
  console.log("[API Debug] askAICore called with:", { text: text.slice(0, 30), documentMode });
  const headers = { "Content-Type": "application/json" };
  const sessionId = localStorage.getItem("medclear_session_id");
  if (sessionId) headers["X-Session-ID"] = sessionId;

  const response = await fetch(AI_CORE_URL, {
    method: "POST",
    headers,
    body: JSON.stringify({ 
      text: text, 
      document_mode: documentMode,
      stream: true 
    }),
  });

  if (!response.ok) {
    throw new Error(`AI core request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  
  let fullReply = "";
  let buffer = ""; // <--- A buffer catches chopped up network packets

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    
    // Split safely only when a full event (\n\n) has arrived
    const parts = buffer.split("\n\n");
    
    // The last part might be an incomplete packet, save it for the next loop
    buffer = parts.pop();

    for (const line of parts) {
      if (line.startsWith("data:")) {
        // Strip the data prefix, safely keeping the JSON string
        const rawData = line.replace(/^data:\s*/, "");

        if (rawData === "[DONE]") {
          return { reply: fullReply.trim(), resolved: true, language: "en" };
        }
        if (rawData.startsWith("[ERROR]")) {
          throw new Error(rawData);
        }

        try {
          // Parse the JSON object payload to safely extract the text (and spaces!)
          const parsed = JSON.parse(rawData);
          
          if (parsed && typeof parsed.text === "string") {
            const textData = parsed.text;
            fullReply += textData;
            
            if (onChunk) {
              onChunk(textData);
            }
          }
        } catch (e) {
          console.warn("Failed to parse chunk:", rawData);
        }
      }
    }
  }

  return { reply: fullReply.trim(), resolved: true, language: "en" };
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