import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import ActionItemCard from '@/components/ActionItemCard'
import MeetingTimeline from '@/components/MeetingTimeline'

interface TimelineItem {
  timestamp: string
  topic: string
}

interface ActionItem {
  id: string
  meeting_id: string
  description: string
  assignee: string | null
  deadline: string | null
  is_edited: boolean
  created_at: string
}

interface MeetingReport {
  id: string
  title: string | null
  summary: string | null
  decisions: string[]
  action_item_ids: string[]
  timeline: TimelineItem[]
  state: string
  started_at: string | null
  ended_at: string | null
  duration_seconds: number | null
}

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function formatDuration(seconds: number | null): string {
  if (seconds === null) return 'N/A'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

export default function PostMeetingReport() {
  const { meetingId } = useParams<{ meetingId: string }>()
  const navigate = useNavigate()
  const { token } = useAuth()

  const [report, setReport] = useState<MeetingReport | null>(null)
  const [actionItems, setActionItems] = useState<ActionItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const authHeaders = useCallback(() => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }), [token])

  // Fetch meeting report
  useEffect(() => {
    if (!meetingId || !token) return

    async function loadReport() {
      setLoading(true)
      setError(null)

      try {
        const resp = await fetch(`${API_BASE}/meetings/${meetingId}`, {
          headers: authHeaders(),
        })

        if (!resp.ok) {
          if (resp.status === 403) {
            setError('You do not have access to this meeting report.')
          } else if (resp.status === 404) {
            setError('Meeting not found.')
          } else {
            setError('Failed to load meeting report.')
          }
          return
        }

        const data: MeetingReport = await resp.json()
        setReport(data)

        // Fetch action items individually by ID
        if (data.action_item_ids && data.action_item_ids.length > 0) {
          const items = await Promise.allSettled(
            data.action_item_ids.map((itemId) =>
              fetch(`${API_BASE}/action-items/${itemId}`, {
                headers: authHeaders(),
              }).then((r) => (r.ok ? (r.json() as Promise<ActionItem>) : null))
            )
          )
          const resolved = items
            .filter((r): r is PromiseFulfilledResult<ActionItem | null> => r.status === 'fulfilled')
            .map((r) => r.value)
            .filter((item): item is ActionItem => item !== null)
          setActionItems(resolved)
        }
      } catch {
        setError('Network error. Please try again.')
      } finally {
        setLoading(false)
      }
    }

    loadReport()
  }, [meetingId, token, authHeaders])

  async function handleSaveActionItem(
    id: string,
    updates: Partial<Pick<ActionItem, 'description' | 'assignee' | 'deadline'>>
  ): Promise<void> {
    const resp = await fetch(`${API_BASE}/meetings/${meetingId}/action-items/${id}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(updates),
    })

    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? 'Save failed')
    }

    const updated: ActionItem = await resp.json()
    setActionItems((prev) => prev.map((item) => (item.id === id ? updated : item)))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-muted-foreground text-sm">Loading meeting report...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <p className="text-destructive text-sm">{error}</p>
        <button
          className="text-sm underline text-muted-foreground"
          onClick={() => navigate('/dashboard')}
        >
          Back to Dashboard
        </button>
      </div>
    )
  }

  if (!report) return null

  const isProcessed = report.state === 'processed'

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">
      {/* Header */}
      <div className="space-y-1">
        <button
          className="text-xs text-muted-foreground underline mb-2 block"
          onClick={() => navigate('/dashboard')}
        >
          Back to Dashboard
        </button>
        <h1 className="text-2xl font-semibold text-foreground">
          {report.title ?? 'Untitled Meeting'}
        </h1>
        <p className="text-sm text-muted-foreground">
          Duration: {formatDuration(report.duration_seconds)}
          {report.ended_at && (
            <span className="ml-4">
              Ended: {new Date(report.ended_at).toLocaleString()}
            </span>
          )}
        </p>
      </div>

      {/* Processing notice */}
      {!isProcessed && (
        <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          Your meeting report is being generated. Refresh this page in a moment to see the full results.
        </div>
      )}

      {/* Summary */}
      {report.summary && (
        <section className="space-y-2">
          <h2 className="text-base font-medium text-foreground">Summary</h2>
          <p className="text-sm text-foreground leading-relaxed whitespace-pre-line">
            {report.summary}
          </p>
        </section>
      )}

      {/* Decisions */}
      {report.decisions && report.decisions.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-base font-medium text-foreground">Decisions</h2>
          <ul className="space-y-1">
            {report.decisions.map((decision, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-foreground">
                <span className="mt-1 shrink-0 size-1.5 rounded-full bg-primary" />
                {decision}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Action Items */}
      <section className="space-y-3">
        <h2 className="text-base font-medium text-foreground">
          Action Items
          {actionItems.length > 0 && (
            <span className="ml-2 text-xs text-muted-foreground font-normal">
              ({actionItems.length})
            </span>
          )}
        </h2>
        {actionItems.length === 0 ? (
          <p className="text-sm text-muted-foreground">No action items recorded.</p>
        ) : (
          <div className="space-y-3">
            {actionItems.map((item) => (
              <ActionItemCard key={item.id} item={item} onSave={handleSaveActionItem} />
            ))}
          </div>
        )}
      </section>

      {/* Meeting Timeline */}
      <section className="space-y-3">
        <h2 className="text-base font-medium text-foreground">Meeting Timeline</h2>
        <MeetingTimeline timeline={report.timeline ?? []} />
      </section>
    </div>
  )
}
