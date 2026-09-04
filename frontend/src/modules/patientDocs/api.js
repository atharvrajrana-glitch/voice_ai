/**
 * Talks to the patient document RAG backend.
 *
 * uploadPatientDocument(file, sessionId) -> { success, chunks_added, message }
 * askPatientDocument(question, sessionId) -> { reply, resolved, language_code, source }
 */

// Helper to get API URL dynamically based on where the app is accessed from
const getApiUrl = () => {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  // Use current host - if accessed from localhost, backend is localhost
  // If accessed from IP, backend is the same IP
  const protocol = window.location.protocol;
  const host = window.location.hostname;
  const port = window.location.port ? `:${window.location.port === '5173' ? '8080' : window.location.port}` : '';
  return `${protocol}//${host}${port}`;
};

const BASE_URL = getApiUrl();

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