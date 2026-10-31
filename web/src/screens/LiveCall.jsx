import { useRef, useState } from "react";
import { sendAudioCall, sendTextCall } from "../api";

const TABS = ["advocate", "challenger", "judge"];

export default function LiveCall() {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [activeTab, setActiveTab] = useState("advocate");
  const [manualText, setManualText] = useState("");

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        submitAudio(blob);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch (err) {
      setError(`Mic access failed: ${err.message}`);
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  async function submitAudio(blob) {
    setBusy(true);
    setError(null);
    try {
      const data = await sendAudioCall(blob);
      setResult(data);
      setActiveTab("advocate");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitText() {
    if (!manualText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const data = await sendTextCall(manualText.trim());
      setResult(data);
      setActiveTab("advocate");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen">
      <h2>Live Call</h2>

      <div className="card">
        <button
          className={recording ? "record-btn recording" : "record-btn"}
          onClick={recording ? stopRecording : startRecording}
          disabled={busy}
        >
          {recording ? "Stop recording" : "Start recording"}
        </button>

        <div className="manual-fallback">
          <textarea
            placeholder="...or paste/type a transcript (text endpoint, no Sarvam credits)"
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            rows={3}
          />
          <button onClick={submitText} disabled={busy || !manualText.trim()}>
            Submit text
          </button>
        </div>

        {busy && <p className="status">Processing…</p>}
        {error && <p className="status error">{error}</p>}
      </div>

      {result && (
        <div className="card result">
          <div className="badge-row">
            <span className={`badge ${result.source}`}>
              {result.source === "cache" ? "Reused verdict" : "New problem: courtroom"}
            </span>
            <span className={`badge risk-${result.risk_level}`}>
              risk: {result.risk_level}
            </span>
            {result.escalate_to_human && (
              <span className="badge escalate">Escalate to human</span>
            )}
          </div>

          <p className="transcript">
            <strong>Transcribed by Sarvam AI{result.language_code ? ` (${result.language_code})` : ""}:</strong>{" "}
            {result.transcript}
          </p>

          <p className="category">
            {result.category} :: {result.subcategory}
          </p>
          <p className="summary">{result.summary}</p>

          <div className="verdict-card">
            <h3>Verdict</h3>
            <p>{result.verdict}</p>
          </div>

          {result.courtroom && (
            <div className="courtroom">
              <h3>AI Courtroom</h3>
              <div className="tabs">
                {TABS.map((tab) => (
                  <button
                    key={tab}
                    className={activeTab === tab ? "tab active" : "tab"}
                    onClick={() => setActiveTab(tab)}
                  >
                    {tab[0].toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>
              <p className="tab-content">{result.courtroom[activeTab]}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}