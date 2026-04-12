import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DocumentUpload } from "@/components/DocumentUpload";
import ArniVisualizer from "@/components/ArniVisualizer";
import DailyIframe from "@daily-co/daily-js";
import {
  DailyProvider,
  useDaily,
  useParticipantIds,
  useDailyEvent,
  DailyVideo,
  DailyAudio,
  useParticipant,
} from "@daily-co/daily-react";

interface Meeting {
  id: string;
  title: string | null;
  state: string;
  host_id: string;
  daily_room_name: string | null;
  daily_room_url: string | null;
}

interface JoinResponse {
  meeting: Meeting;
  daily_token: string;
  daily_room_url: string;
}

interface MeetingParticipant {
  id: string;
  name: string;
  email: string;
  is_host: boolean;
}

interface Transcript {
  id?: string;
  meeting_id: string;
  speaker_id: string;
  speaker_name?: string;
  text: string;
  is_final: boolean;
  timestamp: string;
}

interface WakeWordEvent {
  type: "wake_word";
  speaker_id: string;
  speaker_name: string;
  command: string;
  timestamp: number;
}

type ArniState = "listening" | "processing" | "speaking";

interface AiStateChangedEvent {
  type: "ai.state_changed";
  state: ArniState;
}

const AI_STATE_LABEL: Record<ArniState, string> = {
  listening: "Arni is listening...",
  processing: "Arni is generating a response...",
  speaking: "Arni is speaking...",
};

const AI_STATE_COLOR: Record<ArniState, string> = {
  listening: "text-sky-400",
  processing: "text-yellow-400",
  speaking: "text-emerald-400",
};

function ArniStatusIndicator({ state }: { state: ArniState }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-card/80 border border-border text-xs">
      <span
        className={[
          "inline-block w-2 h-2 rounded-full animate-pulse",
          state === "listening" ? "bg-sky-400" : state === "processing" ? "bg-yellow-400" : "bg-emerald-400",
        ].join(" ")}
      />
      <span className={AI_STATE_COLOR[state]}>{AI_STATE_LABEL[state]}</span>
    </div>
  );
}

function MeetingRoomContent() {
  const { inviteCode } = useParams<{ inviteCode: string }>();
  const { user, token } = useAuth();
  const navigate = useNavigate();
  const daily = useDaily();
  const participantIds = useParticipantIds();

  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isJoining, setIsJoining] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [isCameraOff, setIsCameraOff] = useState(false);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [interimTranscripts, setInterimTranscripts] = useState<Record<string, { text: string; speaker_name: string }>>({});
  const [wakeWordEvent, setWakeWordEvent] = useState<WakeWordEvent | null>(null);
  const wakeWordTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [arniState, setArniState] = useState<ArniState>("listening");
  const [isRecordingPTT, setIsRecordingPTT] = useState(false);
  const [isDocsOpen, setIsDocsOpen] = useState(false);
  interface MeetingDoc { id: string; filename: string; status: string; chunk_count: number; file_size_bytes: number; }
  const [meetingDocs, setMeetingDocs] = useState<MeetingDoc[]>([]);
  const [showEndConfirm, setShowEndConfirm] = useState(false);
  const [isEnding, setIsEnding] = useState(false);
  const [meetingEnded, setMeetingEnded] = useState(false);
  const [summaryText, setSummaryText] = useState<string | null>(null);
  const [summaryTime, setSummaryTime] = useState<string | null>(null);
  const [isSummaryOpen, setIsSummaryOpen] = useState(false);
  const [duration, setDuration] = useState(0);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Participant management (host-only)
  const [isParticipantsOpen, setIsParticipantsOpen] = useState(false);
  const [meetingParticipants, setMeetingParticipants] = useState<MeetingParticipant[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteStatus, setInviteStatus] = useState<string | null>(null);
  const isHost = meeting?.host_id === user?.id;

  // Meeting duration timer
  useEffect(() => {
    const timer = setInterval(() => setDuration((prev) => prev + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  function formatTimer(seconds: number) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  // Auto-scroll transcript to bottom on new messages
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcripts]);

  // Load existing documents for this meeting
  useEffect(() => {
    if (!meeting?.id || !token) return;
    fetch(`/api/meetings/${meeting.id}/documents`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.ok ? r.json() : [])
      .then((docs) => setMeetingDocs(docs))
      .catch(() => {});
  }, [meeting?.id, token]);

  // Load participants
  function loadParticipants() {
    if (!meeting?.id || !token) return;
    fetch(`/api/meetings/${meeting.id}/participants`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.ok ? r.json() : [])
      .then((p) => setMeetingParticipants(p))
      .catch(() => {});
  }

  useEffect(() => {
    loadParticipants();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meeting?.id, token]);

  async function handleInvite() {
    if (!meeting?.id || !inviteEmail.trim()) return;
    setInviteStatus(null);
    try {
      const res = await fetch(`/api/meetings/${meeting.id}/invite`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ email: inviteEmail.trim().toLowerCase() }),
      });
      if (res.ok) {
        setInviteStatus(`Invited ${inviteEmail.trim()}`);
        setInviteEmail("");
      } else {
        const err = await res.json();
        setInviteStatus(err.detail || "Failed to invite");
      }
    } catch {
      setInviteStatus("Failed to invite");
    }
    setTimeout(() => setInviteStatus(null), 3000);
  }

  async function handleRemoveParticipant(userId: string) {
    if (!meeting?.id) return;
    try {
      const res = await fetch(`/api/meetings/${meeting.id}/participants/${userId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        loadParticipants();
      }
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!meeting?.id) return;

    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/api/transcripts/${meeting.id}/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle AI state change events
        if (data.type === "ai.state_changed") {
          const evt = data as AiStateChangedEvent;
          if (evt.state === "listening" || evt.state === "processing" || evt.state === "speaking") {
            setArniState(evt.state);
          }
          return;
        }

        // Handle wake word events — show overlay + append note to transcript
        if (data.type === "wake_word") {
          setWakeWordEvent(data as WakeWordEvent);
          if (wakeWordTimerRef.current) {
            clearTimeout(wakeWordTimerRef.current);
          }
          wakeWordTimerRef.current = setTimeout(() => {
            setWakeWordEvent(null);
          }, 3000);
          setTranscripts((prev) => [...prev, {
            meeting_id: meeting.id,
            speaker_id: "arni",
            speaker_name: "Arni",
            text: `Heard: "${data.command}"`,
            is_final: true,
            timestamp: new Date().toISOString(),
          }]);
          return;
        }

        // Handle Arni's spoken response after wake word
        if (data.type === "ai_response") {
          setTranscripts((prev) => [...prev, {
            meeting_id: meeting.id,
            speaker_id: "arni",
            speaker_name: "Arni",
            text: data.text,
            is_final: true,
            timestamp: new Date().toISOString(),
          }]);
          return;
        }

        // Handle participant removal — redirect if current user was removed
        if (data.type === "participant.removed" && data.user_id === user?.id) {
          alert("You have been removed from this meeting");
          if (daily) daily.leave();
          navigate("/dashboard");
          return;
        }

        // Handle meeting.ended event (broadcast by host ending the meeting)
        if (data.type === "meeting.ended") {
          setMeetingEnded(true);
          setTimeout(async () => {
            if (daily) await daily.leave();
            navigate(`/report/${meeting.id}`);
          }, 3000);
          return;
        }

        // Handle rolling summary update (text only, no audio)
        if (data.type === "summary.updated") {
          setSummaryText(data.summary_text || null);
          setSummaryTime(data.timestamp || null);
          return;
        }

        // Handle Arni memory-based opening in reconvened meetings
        if (data.type === "arni_message") {
          setTranscripts((prev) => [...prev, {
            meeting_id: meeting.id,
            speaker_id: "arni",
            speaker_name: "Arni",
            text: data.text,
            is_final: true,
            timestamp: new Date().toISOString(),
          }]);
          return;
        }

        // Handle transcript events
        if (data.is_final) {
          setTranscripts((prev) => [...prev, data as Transcript]);
          setInterimTranscripts((prev) => {
            const next = { ...prev };
            delete next[data.speaker_id];
            return next;
          });
        } else {
          setInterimTranscripts((prev) => ({
            ...prev,
            [data.speaker_id]: { text: data.text, speaker_name: data.speaker_name || data.speaker_id },
          }));
        }
      } catch (err) {
        console.error("Failed to parse transcript message:", err);
      }
    };

    return () => {
      ws.close();
      if (wakeWordTimerRef.current) {
        clearTimeout(wakeWordTimerRef.current);
      }
    };
  }, [meeting?.id]);

  // Handle call state changes
  useDailyEvent("joined-meeting", () => {
    console.log("Joined meeting successfully");
    setIsJoining(false);
  });

  useDailyEvent("left-meeting", () => {
    console.log("Left meeting");
    navigate("/dashboard");
  });

  useDailyEvent("error", (event) => {
    console.error("Daily error:", event);
    setError("An error occurred during the call");
  });

  useEffect(() => {
    loadMeetingAndJoin();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inviteCode]);

  async function loadMeetingAndJoin() {
    if (!inviteCode || !token) return;

    setIsLoading(true);
    setError(null);

    try {
      // Step 1: Get meeting by invite code
      const meetingRes = await fetch(`/api/meetings/code/${inviteCode}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!meetingRes.ok) {
        throw new Error("Meeting not found");
      }

      const meetingData: Meeting = await meetingRes.json();
      setMeeting(meetingData);

      // Check if Daily.co is configured
      if (!meetingData.daily_room_url) {
        setError(
          "This meeting does not have video calling enabled. Daily.co API key is not configured.",
        );
        setIsLoading(false);
        return;
      }

      // Step 2: Join the meeting to get Daily.co token
      setIsJoining(true);
      const joinRes = await fetch(`/api/meetings/${meetingData.id}/join`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!joinRes.ok) {
        const errorData = await joinRes.json().catch(() => ({}));
        if (joinRes.status === 403) {
          setError("You are not invited to this meeting. Ask the host to add your email to the invite list.");
          setIsJoining(false);
          setIsLoading(false);
          return;
        }
        throw new Error(errorData.detail || "Failed to join meeting");
      }

      const joinData: JoinResponse = await joinRes.json();

      // Step 3: Join Daily.co call
      if (daily) {
        await daily.join({
          url: joinData.daily_room_url,
          token: joinData.daily_token,
        });
      }
    } catch (err: unknown) {
      console.error("Failed to join meeting:", err);
      setError(err instanceof Error ? err.message : "Failed to join meeting");
      setIsJoining(false);
    } finally {
      setIsLoading(false);
    }
  }

  async function toggleMute() {
    if (!daily) return;
    const newMuted = !isMuted;
    await daily.setLocalAudio(!newMuted);
    setIsMuted(newMuted);
  }

  async function toggleCamera() {
    if (!daily) return;
    const newCameraOff = !isCameraOff;
    await daily.setLocalVideo(!newCameraOff);
    setIsCameraOff(newCameraOff);
  }

  async function leaveMeeting() {
    if (daily) {
      await daily.leave();
    }
    navigate("/dashboard");
  }

  async function startPTT() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        if (blob.size === 0 || !meeting?.id) return;

        setArniState("processing");
        try {
          // Step 1: Transcribe the audio
          const txForm = new FormData();
          txForm.append("audio", blob, "recording.webm");

          const txRes = await fetch("/api/ai/transcribe", {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: txForm,
          });
          if (!txRes.ok) throw new Error("Transcription failed");
          const { transcript } = await txRes.json();
          if (!transcript) { setArniState("listening"); return; }

          // Step 2: Send transcript to AI respond endpoint
          const res = await fetch("/api/ai/respond", {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              meeting_id: meeting.id,
              command: transcript,
              speaker_id: "local-user",
            }),
          });

          if (!res.ok) throw new Error("AI respond failed");
          setArniState("speaking");
          setTimeout(() => setArniState("listening"), 5000);
        } catch (err) {
          console.error("Push-to-talk pipeline failed:", err);
          setArniState("listening");
        }
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecordingPTT(true);
    } catch (err) {
      // Mic permission denied or unavailable
    }
  }

  function stopPTT() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    setIsRecordingPTT(false);
  }

  async function handleEndMeeting() {
    if (!meeting?.id) return;
    setIsEnding(true);
    try {
      const res = await fetch(`/api/meetings/${meeting.id}/end`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to end meeting" }));
        alert(err.detail || "Failed to end meeting");
        setIsEnding(false);
        return;
      }
      setMeetingEnded(true);
      setTimeout(async () => {
        if (daily) await daily.leave();
        navigate(`/report/${meeting.id}`);
      }, 2000);
    } catch {
      alert("Failed to end meeting");
      setIsEnding(false);
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="p-12">
          <div className="text-center space-y-4">
            <div className="text-lg font-medium">Loading meeting...</div>
          </div>
        </Card>
      </div>
    );
  }

  if (error) {
    const isAccessDenied = error.toLowerCase().includes("not invited");
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="p-12 max-w-md">
          <div className="text-center space-y-4">
            <h2 className="text-xl font-semibold text-destructive">
              {isAccessDenied ? "Access Denied" : "Error"}
            </h2>
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button onClick={() => navigate("/dashboard")}>
              Back to Dashboard
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      {/* Header */}
      <header className="bg-card border-b border-border px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="font-semibold">
            {meeting?.title || "Untitled Meeting"}
          </h1>
          <p className="text-xs text-muted-foreground flex items-center gap-2">
            <span>
              {participantIds.length} participant
              {participantIds.length !== 1 ? "s" : ""}
            </span>
            <span className="font-mono opacity-70">{formatTimer(duration)}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isHost && (
            <Button variant="destructive" onClick={() => setShowEndConfirm(true)} size="sm">
              End Meeting
            </Button>
          )}
          <Button variant="secondary" onClick={leaveMeeting} size="sm">
            Leave Meeting
          </Button>
        </div>
      </header>

      {/* End Meeting confirmation dialog */}
      {showEndConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <Card className="p-6 max-w-sm space-y-4">
            <h2 className="text-lg font-semibold">End Meeting?</h2>
            <p className="text-sm text-muted-foreground">
              End meeting for all participants? This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setShowEndConfirm(false)} disabled={isEnding}>
                Cancel
              </Button>
              <Button variant="destructive" size="sm" onClick={handleEndMeeting} disabled={isEnding}>
                {isEnding ? "Ending..." : "End Meeting"}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Meeting ended overlay */}
      {meetingEnded && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
          <Card className="p-8">
            <div className="text-center space-y-3">
              <h2 className="text-xl font-semibold">Meeting Ended</h2>
              <p className="text-sm text-muted-foreground">Processing your meeting report...</p>
              <p className="text-xs text-muted-foreground animate-pulse">Redirecting...</p>
            </div>
          </Card>
        </div>
      )}

      <main className="flex-1 p-4 flex gap-4 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          {isJoining ? (
            <div className="h-full flex items-center justify-center">
              <Card className="p-8">
                <div className="text-center text-muted-foreground">
                  Joining meeting...
                </div>
              </Card>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              {participantIds.length === 0 ? (
                <Card className="p-12 col-span-full">
                  <div className="text-center text-muted-foreground">
                    Waiting for participants to join...
                  </div>
                </Card>
              ) : (
                <>
                  {participantIds.map((participantId) => (
                    <ParticipantTile
                      key={participantId}
                      participantId={participantId}
                    />
                  ))}
                  <Card className="relative aspect-video bg-slate-900 dark:bg-slate-900 overflow-hidden">
                    <ArniVisualizer state={arniState === "listening" ? "listening" : arniState} />
                    <div className="absolute bottom-2 left-2 bg-black/70 px-3 py-1 rounded text-sm text-white">
                      Arni
                    </div>
                  </Card>
                </>
              )}
            </div>
          )}
        </div>

        {/* Right sidebar: Summary + Documents + Transcript */}
        <div className="w-80 hidden lg:flex flex-col gap-3">

        {/* Rolling Summary Panel */}
        {summaryText && (
          <Card className="bg-card border-border flex-shrink-0">
            <button
              className="w-full p-3 text-left text-sm font-semibold text-foreground flex items-center justify-between hover:bg-muted/50 transition-colors"
              onClick={() => setIsSummaryOpen(!isSummaryOpen)}
            >
              <span>Meeting Summary</span>
              <span className="text-xs text-muted-foreground">{isSummaryOpen ? "▲" : "▼"}</span>
            </button>
            {isSummaryOpen && (
              <div className="px-3 pb-3">
                <p className="text-sm text-foreground/80 whitespace-pre-wrap">{summaryText}</p>
                {summaryTime && (
                  <p className="text-xs text-muted-foreground/60 mt-2">
                    Last updated {new Date(summaryTime).toLocaleTimeString()}
                  </p>
                )}
              </div>
            )}
          </Card>
        )}

        {/* Document Panel */}
        <Card className="bg-card border-border flex-shrink-0">
          <button
            className="w-full p-3 text-left text-sm font-semibold text-foreground flex items-center justify-between hover:bg-muted/50 transition-colors"
            onClick={() => setIsDocsOpen(!isDocsOpen)}
          >
            <span>Documents ({meetingDocs.length})</span>
            <span className="text-xs text-muted-foreground">{isDocsOpen ? "Hide" : "Show"}</span>
          </button>
          {isDocsOpen && (
            <div className="px-3 pb-3">
              <DocumentUpload
                meetingId={meeting?.id || ""}
                token={token || ""}
                onDocumentReady={(doc) => setMeetingDocs((prev) => [...prev, doc])}
              />
              {meetingDocs.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {meetingDocs.map((doc) => (
                    <li key={doc.id} className="flex items-center justify-between text-xs text-muted-foreground px-1">
                      <span className="truncate">{doc.filename}</span>
                      <span className={doc.status === "ready" ? "text-green-600 dark:text-green-400" : "text-yellow-600 dark:text-yellow-400"}>
                        {doc.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>

        {/* Participants Panel (host only) */}
        {isHost && (
          <Card className="bg-card border-border flex-shrink-0">
            <button
              className="w-full p-3 text-left text-sm font-semibold text-foreground flex items-center justify-between hover:bg-muted/50 transition-colors"
              onClick={() => { setIsParticipantsOpen(!isParticipantsOpen); if (!isParticipantsOpen) loadParticipants(); }}
            >
              <span>Participants ({meetingParticipants.length})</span>
              <span className="text-xs text-muted-foreground">{isParticipantsOpen ? "Hide" : "Show"}</span>
            </button>
            {isParticipantsOpen && (
              <div className="px-3 pb-3 space-y-3">
                {/* Invite input */}
                <div className="flex gap-2">
                  <Input
                    type="email"
                    placeholder="Email to invite"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleInvite(); } }}
                    className="h-8 text-xs"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs shrink-0"
                    onClick={handleInvite}
                    disabled={!inviteEmail.trim()}
                  >
                    Invite
                  </Button>
                </div>
                {inviteStatus && (
                  <p className="text-xs text-emerald-600 dark:text-emerald-400">{inviteStatus}</p>
                )}

                {/* Participant list */}
                <ul className="space-y-1">
                  {meetingParticipants.map((p) => (
                    <li key={p.id} className="flex items-center justify-between text-xs text-foreground/80 px-1 py-1">
                      <div className="truncate">
                        <span>{p.name}</span>
                        {p.is_host && <span className="ml-1.5 text-yellow-600 dark:text-yellow-400">(Host)</span>}
                        <span className="block text-muted-foreground truncate">{p.email}</span>
                      </div>
                      {!p.is_host && (
                        <button
                          className="ml-2 text-muted-foreground hover:text-red-500 shrink-0"
                          onClick={() => handleRemoveParticipant(p.id)}
                          title="Remove participant"
                        >
                          &times;
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        )}

        {/* Live Transcript Panel */}
        <Card className="bg-card border-border flex-1 flex flex-col min-h-0">
          <div className="p-3 border-b border-border font-semibold text-sm text-foreground shadow-sm flex items-center justify-between">
            <span>Live Transcript</span>
            <div className="flex items-center gap-2">
              <ArniStatusIndicator state={arniState} />
              {wakeWordEvent && (
                <span className="text-xs text-emerald-600 dark:text-emerald-400 animate-pulse">● Triggered</span>
              )}
            </div>
          </div>

          {/* Wake word indicator */}
          {wakeWordEvent && (
            <div className="mx-3 mt-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 animate-in fade-in slide-in-from-top-2 duration-300">
              <div className="flex items-center gap-2 text-sm font-medium text-emerald-600 dark:text-emerald-400">
                <span className="text-lg">🤖</span>
                <span>Arni heard you!</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1 pl-7">
                <span className="text-muted-foreground/70">{wakeWordEvent.speaker_name}:</span>{" "}
                "{wakeWordEvent.command}"
              </p>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {transcripts.map((t, i) => {
              const isArni = t.speaker_id === "arni" || t.speaker_name === "Arni";
              return (
                <div key={i} className="text-sm">
                  <span className={`font-semibold ${isArni ? "text-violet-600 dark:text-violet-400" : "text-primary"}`}>
                    {t.speaker_name || t.speaker_id}:{" "}
                  </span>
                  <span className="text-foreground/80">{t.text}</span>
                </div>
              );
            })}

            {Object.entries(interimTranscripts).map(([speakerId, { text, speaker_name }]) => (
              <div key={`interim-${speakerId}`} className="text-sm italic opacity-70">
                <span className="font-semibold text-primary">{speaker_name}: </span>
                <span className="text-foreground/80 animate-pulse">{text}</span>
              </div>
            ))}
            <div ref={transcriptEndRef} />
          </div>
        </Card>
        </div>{/* end right sidebar */}
      </main>

      {/* Controls */}
      <footer className="bg-card border-t border-border px-6 py-4">
        <div className="flex items-center justify-center gap-3">
          <Button
            variant={isMuted ? "destructive" : "secondary"}
            onClick={toggleMute}
          >
            {isMuted ? "Unmute" : "Mute"}
          </Button>
          <Button
            variant={isCameraOff ? "destructive" : "secondary"}
            onClick={toggleCamera}
          >
            {isCameraOff ? "Turn On Camera" : "Turn Off Camera"}
          </Button>

        </div>
      </footer>
      <DailyAudio />
    </div>
  );
}

interface ParticipantTileProps {
  participantId: string;
}

function ParticipantTile({ participantId }: ParticipantTileProps) {
  const participant = useParticipant(participantId);

  if (!participant) {
    return (
      <Card className="relative aspect-video bg-muted overflow-hidden flex items-center justify-center">
        <span className="text-sm text-muted-foreground animate-pulse">Loading participant...</span>
      </Card>
    );
  }

  // Hide Daily.co Arni Bot tile — ArniVisualizer is shown separately
  const name = (participant.user_name || "").toLowerCase();
  if (name.includes("arni")) return null;

  const videoTrack = participant.tracks?.video;
  const audioTrack = participant.tracks?.audio;
  const isLocal = participant.local;

  return (
    <Card className="relative aspect-video bg-muted overflow-hidden">
      {/* Video element */}
      {videoTrack?.state === "playable" ? (
        <DailyVideo
          sessionId={participantId}
          type="video"
          mirror={isLocal}
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-muted">
          <div className="text-4xl font-bold text-muted-foreground">
            {participant.user_name?.[0]?.toUpperCase() || "?"}
          </div>
        </div>
      )}

      {/* Name badge */}
      <div className="absolute bottom-2 left-2 bg-black/70 px-3 py-1 rounded text-sm text-white">
        {participant.user_name || "Guest"} {isLocal && "(You)"}
      </div>

      {/* Audio indicator */}
      {audioTrack?.state === "off" && (
        <div className="absolute top-2 right-2 bg-red-500 px-2 py-1 rounded text-xs text-white">
          Muted
        </div>
      )}
    </Card>
  );
}

export default function MeetingRoom() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [callObject, setCallObject] = useState<any>(null);

  useEffect(() => {
    const daily = DailyIframe.createCallObject({
      audioSource: true,
      videoSource: true,
    });
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCallObject(daily);

    return () => {
      daily.destroy();
    };
  }, []);

  if (!callObject) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-muted-foreground">Initializing...</div>
      </div>
    );
  }

  return (
    <DailyProvider callObject={callObject}>
      <MeetingRoomContent />
    </DailyProvider>
  );
}
