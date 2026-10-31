const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export function sendTextCall(transcript) {
  return request("/api/calls/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });
}

export function sendAudioCall(blob) {
  const form = new FormData();
  form.append("file", blob, "call.webm");
  return request("/api/calls", { method: "POST", body: form });
}

export function getDashboard() {
  return request("/api/dashboard");
}

export function getMindmap() {
  return request("/api/mindmap");
}

export function resetDemo() {
  return request("/api/reset", { method: "POST" });
}