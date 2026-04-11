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
import { DocumentUpload } from "@/components/DocumentUpload";
import { useState, useEffect, useCallback, useRef } from "react";

interface Meeting {
  id: string;
  title: string | null;
  state: string;
  invite_code: string;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  participant_count: number;
  action_item_count: number;
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

function Dashboard() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newMeetingTitle, setNewMeetingTitle] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createdMeeting, setCreatedMeeting] = useState<MeetingDetail | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [createStep, setCreateStep] = useState<"title" | "documents" | "done">("title");
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedQuery = useDebounce(searchQuery, 300);
  const abortRef = useRef<AbortController | null>(null);

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
          // silently ignore abort, log real errors
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

  async function handleCreateMeeting(e: React.FormEvent) {
    e.preventDefault();
    setIsCreating(true);

    try {
      const res = await fetch("/api/meetings/create", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: newMeetingTitle || undefined,
        }),
      });

      if (res.ok) {
        const meeting: MeetingDetail = await res.json();
        setCreatedMeeting(meeting);
        setNewMeetingTitle("");
        setCreateStep("documents");
        await loadMeetings(debouncedQuery);
      } else {
        const error = await res.json();
        alert(error.detail || "Failed to create meeting");
      }
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
              if (!open) { setCreateStep("title"); setCreatedMeeting(null); }
            }}>
              <DialogTrigger asChild>
                <Button>Create Meeting</Button>
              </DialogTrigger>
              <DialogContent>
                {createStep === "title" && (
                  <>
                    <DialogHeader>
                      <DialogTitle>Create New Meeting</DialogTitle>
                      <DialogDescription>
                        Step 1 of 2 — Give your meeting a title.
                      </DialogDescription>
                    </DialogHeader>
                    <form onSubmit={handleCreateMeeting}>
                      <div className="space-y-4 py-4">
                        <div className="space-y-2">
                          <Label htmlFor="title">Meeting Title</Label>
                          <Input
                            id="title"
                            placeholder="e.g., Team Standup"
                            value={newMeetingTitle}
                            onChange={(e) => setNewMeetingTitle(e.target.value)}
                            autoFocus
                          />
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
                        <Button type="submit" disabled={isCreating}>
                          {isCreating ? "Creating..." : "Next"}
                        </Button>
                      </DialogFooter>
                    </form>
                  </>
                )}

                {createStep === "documents" && createdMeeting && (
                  <>
                    <DialogHeader>
                      <DialogTitle>Upload Documents (Optional)</DialogTitle>
                      <DialogDescription>
                        Step 2 of 2 — Upload documents for Arni to reference during the meeting.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="py-4">
                      <DocumentUpload
                        meetingId={createdMeeting.id}
                        token={token || ""}
                      />
                    </div>
                    <DialogFooter>
                      <Button
                        variant="outline"
                        onClick={() => setCreateStep("done")}
                      >
                        Skip
                      </Button>
                      <Button onClick={() => setCreateStep("done")}>
                        Done
                      </Button>
                    </DialogFooter>
                  </>
                )}

                {createStep === "done" && createdMeeting && (
                  <>
                    <DialogHeader>
                      <DialogTitle>Meeting Ready!</DialogTitle>
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
                    </div>
                    <DialogFooter>
                      <Button
                        onClick={() => {
                          setCreatedMeeting(null);
                          setCreateStep("title");
                          setIsCreateOpen(false);
                        }}
                      >
                        Done
                      </Button>
                    </DialogFooter>
                  </>
                )}
              </DialogContent>
            </Dialog>
          </div>

          {/* Search bar */}
          <div className="mb-6">
            <Input
              placeholder="Search meetings by title or summary…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="max-w-sm"
            />
          </div>

          {isLoading ? (
            <div className="text-center py-12 text-muted-foreground">
              Loading meetings...
            </div>
          ) : meetings.length === 0 ? (
            <Card className="p-12">
              <div className="text-center space-y-2">
                {searchQuery ? (
                  <>
                    <h2 className="text-xl font-semibold">No results found</h2>
                    <p className="text-sm text-muted-foreground">
                      Try a different search term.
                    </p>
                  </>
                ) : (
                  <>
                    <h2 className="text-xl font-semibold">No meetings yet</h2>
                    <p className="text-sm text-muted-foreground">
                      Create your first meeting to get started.
                    </p>
                  </>
                )}
              </div>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {meetings.map((meeting) => (
                <Card
                  key={meeting.id}
                  className="p-5 hover:shadow-md transition-shadow"
                >
                  <div className="space-y-3">
                    <div>
                      <h3 className="font-semibold text-lg truncate">
                        {meeting.title || "Untitled Meeting"}
                      </h3>
                      <p
                        className={`text-sm font-medium capitalize ${getStateColor(meeting.state)}`}
                      >
                        {meeting.state}
                      </p>
                    </div>

                    <div className="space-y-1 text-sm text-muted-foreground">
                      <div>Created: {formatDate(meeting.created_at)}</div>
                      <div>Participants: {meeting.participant_count}</div>
                      {meeting.action_item_count > 0 && (
                        <div>Action Items: {meeting.action_item_count}</div>
                      )}
                    </div>

                    <div className="flex gap-2 pt-2">
                      {meeting.state === "processed" ? (
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1"
                          onClick={() => navigate(`/report/${meeting.id}`)}
                        >
                          View Report
                        </Button>
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
      </main>
    </div>
  );
}

export default Dashboard;
