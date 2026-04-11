import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
  daily_room_name: string | null;
  daily_room_url: string | null;
}

interface JoinResponse {
  meeting: Meeting;
  daily_token: string;
  daily_room_url: string;
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
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-900/80 border border-gray-700 text-xs">
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
  const { token } = useAuth();
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
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    if (!meeting?.id) return;

    // TODO: configure environment API URL instead of hardcoding localhost if moving to prod
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//localhost:8000/transcripts/${meeting.id}/ws`;
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

        // Handle wake word events
        if (data.type === "wake_word") {
          setWakeWordEvent(data as WakeWordEvent);
          // Clear any existing timer
          if (wakeWordTimerRef.current) {
            clearTimeout(wakeWordTimerRef.current);
          }
          // Auto-dismiss after 3 seconds
          wakeWordTimerRef.current = setTimeout(() => {
            setWakeWordEvent(null);
          }, 3000);
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
        const errorData = await joinRes.json();
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
          const form = new FormData();
          form.append("meeting_id", meeting.id);
          form.append("audio", blob, "recording.webm");

          const res = await fetch("/api/ai/push-to-talk", {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: form,
          });

          if (!res.ok) throw new Error("Push-to-talk failed");
          setArniState("speaking");
          setTimeout(() => setArniState("listening"), 3000);
        } catch (err) {
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
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="p-12 max-w-md">
          <div className="text-center space-y-4">
            <h2 className="text-xl font-semibold text-destructive">Error</h2>
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
    <div className="min-h-screen flex flex-col bg-black">
      {/* Header */}
      <header className="bg-card border-b px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="font-semibold">
            {meeting?.title || "Untitled Meeting"}
          </h1>
          <p className="text-xs text-muted-foreground">
            {participantIds.length} participant
            {participantIds.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Button variant="destructive" onClick={leaveMeeting} size="sm">
          Leave Meeting
        </Button>
      </header>

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
                participantIds.map((participantId) => (
                  <ParticipantTile
                    key={participantId}
                    participantId={participantId}
                  />
                ))
              )}
            </div>
          )}
        </div>

        {/* Live Transcript Panel */}
        <Card className="w-80 bg-gray-950 border-gray-800 hidden lg:flex flex-col">
          <div className="p-3 border-b border-gray-800 font-semibold text-sm text-gray-200 shadow-sm flex items-center justify-between">
            <span>Live Transcript</span>
            <div className="flex items-center gap-2">
              <ArniStatusIndicator state={arniState} />
              {wakeWordEvent && (
                <span className="text-xs text-emerald-400 animate-pulse">● Triggered</span>
              )}
            </div>
          </div>

          {/* Wake word indicator */}
          {wakeWordEvent && (
            <div className="mx-3 mt-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 animate-in fade-in slide-in-from-top-2 duration-300">
              <div className="flex items-center gap-2 text-sm font-medium text-emerald-400">
                <span className="text-lg">🤖</span>
                <span>Arni heard you!</span>
              </div>
              <p className="text-xs text-gray-400 mt-1 pl-7">
                <span className="text-gray-500">{wakeWordEvent.speaker_name}:</span>{" "}
                "{wakeWordEvent.command}"
              </p>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {transcripts.map((t, i) => (
              <div key={i} className="text-sm">
                <span className="font-semibold text-blue-400">
                  {t.speaker_name || t.speaker_id}:{" "}
                </span>
                <span className="text-gray-300">{t.text}</span>
              </div>
            ))}

            {Object.entries(interimTranscripts).map(([speakerId, { text, speaker_name }]) => (
              <div key={`interim-${speakerId}`} className="text-sm italic opacity-70">
                <span className="font-semibold text-blue-400">{speaker_name}: </span>
                <span className="text-gray-300 animate-pulse">{text}</span>
              </div>
            ))}
          </div>
        </Card>
      </main>

      {/* Controls */}
      <footer className="bg-card border-t px-6 py-4">
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

          <Button
            className={[
              "ml-4 px-6 py-3 font-semibold transition-all select-none",
              isRecordingPTT
                ? "bg-red-600 hover:bg-red-700 text-white animate-pulse"
                : "bg-emerald-600 hover:bg-emerald-700 text-white",
            ].join(" ")}
            onPointerDown={startPTT}
            onPointerUp={stopPTT}
            onPointerLeave={stopPTT}
          >
            {isRecordingPTT ? "Recording..." : "Ask Arni"}
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
      <Card className="relative aspect-video bg-gray-900 overflow-hidden flex items-center justify-center">
        <span className="text-sm text-gray-500 animate-pulse">Loading participant...</span>
      </Card>
    );
  }

  const videoTrack = participant.tracks?.video;
  const audioTrack = participant.tracks?.audio;
  const isLocal = participant.local;

  return (
    <Card className="relative aspect-video bg-gray-900 overflow-hidden">
      {/* Video element */}
      {videoTrack?.state === "playable" ? (
        <DailyVideo
          sessionId={participantId}
          type="video"
          mirror={isLocal}
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-gray-800">
          <div className="text-4xl font-bold text-gray-600">
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
