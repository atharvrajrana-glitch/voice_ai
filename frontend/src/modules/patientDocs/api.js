/**
 * Talks to the patient document RAG backend.
 *
 * uploadPatientDocument(file, sessionId) -> { success, chunks_added, message }
 * askPatientDocument(question, sessionId) -> { reply, resolved, language_code, source }
 */

const BASE_URL = "http://localhost:8080";

export async function uploadPatientDocument(file, sessionId) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);

  const response = await fetch(`${BASE_URL}/api/patient-doc/upload`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
  return response.json();
}

export async function askPatientDocument(question, sessionId) {
  const response = await fetch(`${BASE_URL}/api/patient-doc/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!response.ok) throw new Error(`Ask failed: ${response.status}`);
  return response.json();
}