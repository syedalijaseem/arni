import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import ThemeToggle from "@/components/ThemeToggle";
import { useState, useEffect, useCallback, useRef } from "react";

interface Meeting {
  id: string;
  title: string | null;
  host_id: string;
  state: string;
  invite_code: string;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  participant_count: number;
  action_item_count: number;
  reconvened_by: string | null;
}

interface MeetingDetail {
  id: string;
  title: string | null;
  host_id: string;
  participant_ids: string[];
  state: string;
  invite_link: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  created_at: string;
  summary: string | null;
  decisions: string[];
  action_item_ids: string[];
  timeline: unknown[];
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);

  return debounced;
}

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/csv",
  "application/csv",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
];
const MAX_FILE_SIZE = 20 * 1024 * 1024;

function Dashboard() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"active" | "history">("active");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newMeetingTitle, setNewMeetingTitle] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createdMeeting, setCreatedMeeting] = useState<MeetingDetail | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedQuery = useDebounce(searchQuery, 300);
  const abortRef = useRef<AbortController | null>(null);

  // Create dialog form state
  const [inviteEmails, setInviteEmails] = useState<string[]>([]);
  const [emailInput, setEmailInput] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reconvene state
  const [reconveneId, setReconveneId] = useState<string | null>(null);
  const [reconveneTitle, setReconveneTitle] = useState("");
  const [reconveneSummary, setReconveneSummary] = useState("");
  const [isReconvening, setIsReconvening] = useState(false);
  const [reconveneEmails, setReconveneEmails] = useState<string[]>([]);
  const [reconveneEmailInput, setReconveneEmailInput] = useState("");

  const loadMeetings = useCallback(
    async (query: string) => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      setIsLoading(true);
      try {
        const url = query.trim()
          ? `/api/meetings/search?q=${encodeURIComponent(query.trim())}`
          : `/api/meetings/dashboard`;
        const res = await fetch(url, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (res.ok) {
          const data = await res.json();
          setMeetings(data);
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          // silently ignore abort
        }
      } finally {
        setIsLoading(false);
      }
    },
    [token],
  );

  useEffect(() => {
    loadMeetings(debouncedQuery);
  }, [debouncedQuery, loadMeetings]);

  function resetCreateForm() {
    setNewMeetingTitle("");
    setInviteEmails([]);
    setEmailInput("");
    setSelectedFiles([]);
    setCreatedMeeting(null);
    setIsDragging(false);
  }

  function addEmail() {
    const email = emailInput.trim().toLowerCase();
    if (email && email.includes("@") && !inviteEmails.includes(email)) {
      setInviteEmails((prev) => [...prev, email]);
      setEmailInput("");
    }
  }

  function removeEmail(email: string) {
    setInviteEmails((prev) => prev.filter((e) => e !== email));
  }

  function handleEmailKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addEmail();
    }
  }

  function addFiles(files: FileList | File[]) {
    const valid = Array.from(files).filter((f) => {
      if (!ACCEPTED_TYPES.includes(f.type)) return false;
      if (f.size > MAX_FILE_SIZE) return false;
      return !selectedFiles.some((s) => s.name === f.name);
    });
    if (valid.length > 0) {
      setSelectedFiles((prev) => [...prev, ...valid]);
    }
  }

  function removeFile(name: string) {
    setSelectedFiles((prev) => prev.filter((f) => f.name !== name));
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  }

  async function handleCreateMeeting(e: React.FormEvent) {
    e.preventDefault();
    if (!newMeetingTitle.trim()) return;
    setIsCreating(true);

    try {
      // 1. Create the meeting
      const res = await fetch("/api/meetings/create", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ title: newMeetingTitle.trim() }),
      });

      if (!res.ok) {
        const error = await res.json();
        alert(error.detail || "Failed to create meeting");
        return;
      }

      const meeting: MeetingDetail = await res.json();

      // 2. Upload documents (fire and forget — they process async)
      for (const file of selectedFiles) {
        const form = new FormData();
        form.append("file", file);
        fetch(`/api/meetings/${meeting.id}/documents`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        }).catch(() => {});
      }

      // 3. Send invites
      for (const email of inviteEmails) {
        fetch(`/api/meetings/${meeting.id}/invite`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ email }),
        }).catch(() => {});
      }

      setCreatedMeeting(meeting);
      await loadMeetings(debouncedQuery);
    } catch {
      alert("Failed to create meeting");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleDeleteMeeting(meetingId: string) {
    if (!confirm("Are you sure you want to delete this meeting?")) return;

    try {
      const res = await fetch(`/api/meetings/${meetingId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.ok) {
        await loadMeetings(debouncedQuery);
      } else {
        const error = await res.json();
        alert(error.detail || "Failed to delete meeting");
      }
    } catch {
      alert("Failed to delete meeting");
    }
  }

  function copyInviteLink(link: string) {
    navigator.clipboard.writeText(link);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  }

  async function openReconveneDialog(meeting: Meeting) {
    setReconveneId(meeting.id);
    setReconveneTitle(`Follow-up: ${meeting.title || "Untitled Meeting"}`);
    setReconveneEmails([]);
    setReconveneEmailInput("");
    // Fetch meeting detail + participants in parallel
    try {
      const [detailRes, participantsRes] = await Promise.all([
        fetch(`/api/meetings/${meeting.id}`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`/api/meetings/${meeting.id}/participants`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);
      if (detailRes.ok) {
        const detail: MeetingDetail = await detailRes.json();
        setReconveneSummary(detail.summary || "");
      }
      if (participantsRes.ok) {
        const participants: { id: string; email: string; is_host: boolean }[] = await participantsRes.json();
        const emails = participants
          .filter((p) => !p.is_host && p.email)
          .map((p) => p.email.toLowerCase());
        setReconveneEmails(emails);
      }
    } catch {
      // proceed without pre-populated data
    }
  }

  async function handleReconvene() {
    if (!reconveneId) return;
    setIsReconvening(true);
    try {
      const res = await fetch(`/api/meetings/${reconveneId}/reconvene`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ title: reconveneTitle.trim() || null, invite_emails: reconveneEmails }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to reconvene" }));
        alert(err.detail || "Failed to reconvene");
        return;
      }
      const newMeeting: MeetingDetail = await res.json();
      // Copy invite link
      navigator.clipboard.writeText(newMeeting.invite_link);
      // Close dialog and navigate
      setReconveneId(null);
      const code = newMeeting.invite_link.split("/").pop();
      navigate(`/meeting/${code}`);
    } catch {
      alert("Failed to reconvene meeting");
    } finally {
      setIsReconvening(false);
    }
  }

  function formatDate(dateStr: string) {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function getStateColor(state: string) {
    switch (state) {
      case "created":
        return "text-blue-500";
      case "active":
        return "text-green-500";
      case "ended":
        return "text-yellow-500";
      case "processed":
        return "text-gray-500";
      default:
        return "text-gray-400";
    }
  }

  const activeMeetings = meetings.filter(
    (m) => m.state === "created" || m.state === "active",
  );
  const historyMeetings = meetings.filter(
    (m) => m.state === "ended" || m.state === "processed",
  );
  const displayedMeetings = activeTab === "active" ? activeMeetings : historyMeetings;

  function formatDuration(seconds: number | null) {
    if (!seconds) return null;
    const mins = Math.floor(seconds / 60);
    return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="flex items-center justify-between px-6 md:px-12 py-4 border-b bg-card">
        <span className="text-lg font-bold tracking-tight">
          <span className="text-primary">Arni</span>
        </span>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <span className="text-sm text-muted-foreground">{user?.name}</span>
          <Button variant="outline" size="sm" onClick={logout}>
            Sign out
          </Button>
        </div>
      </header>

      <main className="flex-1 px-6 md:px-12 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold">Your Meetings</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Create and manage your meeting rooms
              </p>
            </div>

            <Dialog open={isCreateOpen} onOpenChange={(open) => {
              setIsCreateOpen(open);
              if (!open) resetCreateForm();
            }}>
              <DialogTrigger asChild>
                <Button>Create Meeting</Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-lg">
                {!createdMeeting ? (
                  <>
                    <DialogHeader>
                      <DialogTitle>Create New Meeting</DialogTitle>
                      <DialogDescription>
                        Set up your meeting with optional documents and participants.
                      </DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleCreateMeeting}>
                      <div className="space-y-5 py-4">
                        {/* Title */}
                        <div className="space-y-2">
                          <Label htmlFor="title">Meeting Title *</Label>
                          <Input
                            id="title"
                            placeholder="e.g., Team Standup"
                            value={newMeetingTitle}
                            onChange={(e) => setNewMeetingTitle(e.target.value)}
                            required
                            autoFocus
                          />
                        </div>

                        {/* Documents drop zone */}
                        <div className="space-y-2">
                          <Label>Documents (optional)</Label>
                          <div
                            className={[
                              "border-2 border-dashed rounded-lg p-4 text-center text-sm cursor-pointer transition-colors",
                              isDragging
                                ? "border-primary bg-primary/5"
                                : "border-muted-foreground/25 hover:border-muted-foreground/50",
                            ].join(" ")}
                            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                            onDragLeave={() => setIsDragging(false)}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                          >
                            <input
                              ref={fileInputRef}
                              type="file"
                              accept=".pdf,.docx,.txt,.csv,.xlsx,.xls"
                              multiple
                              className="hidden"
                              onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
                            />
                            <p className="text-muted-foreground">
                              Drop PDF, Word, Text, CSV, or Excel files here
                            </p>
                          </div>
                          {selectedFiles.length > 0 && (
                            <ul className="space-y-1 mt-2">
                              {selectedFiles.map((f) => (
                                <li key={f.name} className="flex items-center justify-between text-sm bg-muted/50 px-3 py-1.5 rounded">
                                  <span className="truncate">{f.name}</span>
                                  <button type="button" className="ml-2 text-muted-foreground hover:text-destructive" onClick={() => removeFile(f.name)}>
                                    &times;
                                  </button>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>

                        {/* Email invites */}
                        <div className="space-y-2">
                          <Label>Invite Participants (optional)</Label>
                          <div className="flex gap-2">
                            <Input
                              type="email"
                              placeholder="colleague@company.com"
                              value={emailInput}
                              onChange={(e) => setEmailInput(e.target.value)}
                              onKeyDown={handleEmailKeyDown}
                            />
                            <Button type="button" variant="outline" size="sm" onClick={addEmail} disabled={!emailInput.trim()}>
                              Add
                            </Button>
                          </div>
                          {inviteEmails.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-2">
                              {inviteEmails.map((email) => (
                                <span key={email} className="inline-flex items-center gap-1 bg-primary/10 text-primary text-xs px-2.5 py-1 rounded-full">
                                  {email}
                                  <button type="button" className="hover:text-destructive" onClick={() => removeEmail(email)}>
                                    &times;
                                  </button>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      <DialogFooter>
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => setIsCreateOpen(false)}
                          disabled={isCreating}
                        >
                          Cancel
                        </Button>
                        <Button type="submit" disabled={isCreating || !newMeetingTitle.trim()}>
                          {isCreating ? "Creating..." : "Create Meeting"}
                        </Button>
                      </DialogFooter>
                    </form>
                  </>
                ) : (
                  <>
                    <DialogHeader>
                      <DialogTitle>Meeting Created</DialogTitle>
                      <DialogDescription>
                        Share this link with participants to join.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                      <div className="space-y-2">
                        <Label>Meeting Title</Label>
                        <div className="font-medium">{createdMeeting.title}</div>
                      </div>
                      <div className="space-y-2">
                        <Label>Invite Link</Label>
                        <div className="flex gap-2">
                          <Input
                            readOnly
                            value={createdMeeting.invite_link}
                            className="font-mono text-sm"
                          />
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => copyInviteLink(createdMeeting.invite_link)}
                          >
                            {copiedLink ? "Copied!" : "Copy"}
                          </Button>
                        </div>
                      </div>
                      {inviteEmails.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                          Invites sent to {inviteEmails.join(", ")}
                        </p>
                      )}
                      {selectedFiles.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                          {selectedFiles.length} document{selectedFiles.length !== 1 ? "s" : ""} uploading
                        </p>
                      )}
                    </div>
                    <DialogFooter className="flex gap-2 sm:gap-2">
                      <Button
                        variant="outline"
                        onClick={() => { resetCreateForm(); setIsCreateOpen(false); }}
                      >
                        Done
                      </Button>
                      <Button
                        onClick={() => {
                          const code = createdMeeting.invite_link.split("/").pop();
                          resetCreateForm();
                          setIsCreateOpen(false);
                          navigate(`/meeting/${code}`);
                        }}
                      >
                        Join Now
                      </Button>
                    </DialogFooter>
                  </>
                )}
              </DialogContent>
            </Dialog>
          </div>

          {/* Search bar + Tabs */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-6">
            <div className="flex rounded-lg border overflow-hidden">
              <button
                className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === "active" ? "bg-primary text-primary-foreground" : "bg-card hover:bg-muted"}`}
                onClick={() => setActiveTab("active")}
              >
                My Meetings ({activeMeetings.length})
              </button>
              <button
                className={`px-4 py-2 text-sm font-medium transition-colors ${activeTab === "history" ? "bg-primary text-primary-foreground" : "bg-card hover:bg-muted"}`}
                onClick={() => setActiveTab("history")}
              >
                History ({historyMeetings.length})
              </button>
            </div>
            <Input
              placeholder="Search meetings by title or summary..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="max-w-sm"
            />
          </div>

          {isLoading ? (
            <div className="text-center py-12 text-muted-foreground">
              Loading meetings...
            </div>
          ) : displayedMeetings.length === 0 ? (
            <Card className="p-12">
              <div className="text-center space-y-2">
                <h2 className="text-xl font-semibold">
                  {activeTab === "active" ? "No active meetings" : "No past meetings"}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {activeTab === "active"
                    ? "Create a meeting to get started."
                    : "Ended meetings will appear here."}
                </p>
              </div>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {displayedMeetings.map((meeting) => (
                <Card
                  key={meeting.id}
                  className="p-5 hover:shadow-md transition-shadow"
                >
                  <div className="space-y-3">
                    <div>
                      <h3 className="font-semibold text-lg truncate">
                        {meeting.title || `Meeting on ${new Date(meeting.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`}
                      </h3>
                      <p
                        className={`text-sm font-medium capitalize ${getStateColor(meeting.state)}`}
                      >
                        {meeting.state}
                      </p>
                    </div>

                    <div className="space-y-1 text-sm text-muted-foreground">
                      <div>{formatDate(meeting.created_at)}</div>
                      <div>Participants: {meeting.participant_count}</div>
                      {meeting.duration_seconds && (
                        <div>Duration: {formatDuration(meeting.duration_seconds)}</div>
                      )}
                      {meeting.action_item_count > 0 && (
                        <div>Action Items: {meeting.action_item_count}</div>
                      )}
                    </div>

                    <div className="flex gap-2 pt-2">
                      {activeTab === "history" ? (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            className="flex-1"
                            onClick={() => navigate(`/report/${meeting.id}`)}
                          >
                            View Report
                          </Button>
                          {meeting.host_id === user?.id && (
                            meeting.reconvened_by ? (
                              <span className="text-xs text-muted-foreground px-2 py-1 bg-muted rounded self-center">
                                Reconvened
                              </span>
                            ) : (
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => openReconveneDialog(meeting)}
                              >
                                Reconvene
                              </Button>
                            )
                          )}
                        </>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1"
                          onClick={() =>
                            navigate(`/meeting/${meeting.invite_code}`)
                          }
                        >
                          Join
                        </Button>
                      )}
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleDeleteMeeting(meeting.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Reconvene dialog */}
        {reconveneId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <Card className="p-6 w-full max-w-md space-y-4">
              <h2 className="text-lg font-semibold">Reconvene Meeting</h2>
              <div className="space-y-3">
                <div className="space-y-1">
                  <Label htmlFor="reconvene-title">Title</Label>
                  <Input
                    id="reconvene-title"
                    value={reconveneTitle}
                    onChange={(e) => setReconveneTitle(e.target.value)}
                    autoFocus
                  />
                </div>
                {/* Participants */}
                <div className="space-y-1">
                  <Label>Participants</Label>
                  <div className="flex gap-2">
                    <Input
                      type="email"
                      placeholder="Add email"
                      value={reconveneEmailInput}
                      onChange={(e) => setReconveneEmailInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === ",") {
                          e.preventDefault();
                          const v = reconveneEmailInput.trim().toLowerCase();
                          if (v && v.includes("@") && !reconveneEmails.includes(v)) {
                            setReconveneEmails((prev) => [...prev, v]);
                            setReconveneEmailInput("");
                          }
                        }
                      }}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const v = reconveneEmailInput.trim().toLowerCase();
                        if (v && v.includes("@") && !reconveneEmails.includes(v)) {
                          setReconveneEmails((prev) => [...prev, v]);
                          setReconveneEmailInput("");
                        }
                      }}
                    >
                      Add
                    </Button>
                  </div>
                  {reconveneEmails.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {reconveneEmails.map((email) => (
                        <span key={email} className="inline-flex items-center gap-1 bg-primary/10 text-primary text-xs px-2.5 py-1 rounded-full">
                          {email}
                          <button type="button" className="hover:text-destructive" onClick={() => setReconveneEmails((prev) => prev.filter((e) => e !== email))}>
                            &times;
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {reconveneSummary && (
                  <div className="space-y-1">
                    <Label>Arni will remember:</Label>
                    <p className="text-sm text-muted-foreground bg-muted/50 rounded p-3">
                      {reconveneSummary.slice(0, 200)}
                      {reconveneSummary.length > 200 ? "..." : ""}
                    </p>
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setReconveneId(null); setReconveneSummary(""); setReconveneEmails([]); }}
                  disabled={isReconvening}
                >
                  Cancel
                </Button>
                <Button size="sm" onClick={handleReconvene} disabled={isReconvening}>
                  {isReconvening ? "Creating..." : "Start Follow-up Meeting"}
                </Button>
              </div>
            </Card>
          </div>
        )}
      </main>
    </div>
  );
}

export default Dashboard;
