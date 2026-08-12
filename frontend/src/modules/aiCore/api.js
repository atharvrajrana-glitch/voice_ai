
const AI_CORE_URL = "http://localhost:8080/api/ai-core";

export async function askAICore(text) {
  const response = await fetch(AI_CORE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) {
    throw new Error(`AI core request failed: ${response.status}`);
  }

  return response.json();
}