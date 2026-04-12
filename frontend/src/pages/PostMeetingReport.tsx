import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import ActionItemCard from '@/components/ActionItemCard'
import MeetingTimeline from '@/components/MeetingTimeline'
import QnAChat from '@/components/QnAChat'
import { Spinner } from '@/components/Spinner'

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

const API_BASE = '/api'

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
      <div className="flex items-center justify-center min-h-screen bg-slate-950">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-950 gap-4">
        <p className="text-red-400 text-sm">{error}</p>
        <button
          className="text-sm text-slate-400 hover:text-white underline transition-colors"
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
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Header */}
      <div className="border-b border-slate-800 px-6 py-4">
        <div className="max-w-6xl mx-auto">
          <button
            className="text-xs text-slate-500 hover:text-slate-300 mb-3 block transition-colors"
            onClick={() => navigate('/dashboard')}
          >
            &larr; Back to Dashboard
          </button>
          <h1 className="text-2xl font-bold text-white">
            {report.title ? `${report.title} — Summary` : 'Meeting Summary'}
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Duration: {formatDuration(report.duration_seconds)}
            {report.ended_at && (
              <span className="ml-4">
                Ended: {new Date(report.ended_at).toLocaleString()}
              </span>
            )}
          </p>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Processing notice */}
        {!isProcessed && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-300 mb-8">
            Your meeting report is being generated. Refresh this page in a moment to see the full results.
          </div>
        )}

        {/* Two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left column — 2/3 */}
          <div className="lg:col-span-2 space-y-8">
            {/* Stats row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-700/40">
                <div className="text-2xl font-bold text-white">{formatDuration(report.duration_seconds)}</div>
                <div className="text-xs text-slate-400 uppercase tracking-wide mt-1">Duration</div>
              </div>
              <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-700/40">
                <div className="text-2xl font-bold text-white">{report.decisions?.length || 0}</div>
                <div className="text-xs text-slate-400 uppercase tracking-wide mt-1">Decisions</div>
              </div>
              <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-700/40">
                <div className="text-2xl font-bold text-white">{actionItems.length}</div>
                <div className="text-xs text-slate-400 uppercase tracking-wide mt-1">Action Items</div>
              </div>
              <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-700/40">
                <div className="text-2xl font-bold text-white">{report.timeline?.length || 0}</div>
                <div className="text-xs text-slate-400 uppercase tracking-wide mt-1">Topics</div>
              </div>
            </div>

            {/* Summary */}
            {report.summary && (
              <section className="border-l-4 border-blue-500 pl-5">
                <h2 className="text-lg font-semibold text-white mb-2">Meeting Summary</h2>
                <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-line">
                  {report.summary}
                </p>
              </section>
            )}

            {/* Decisions */}
            {report.decisions && report.decisions.length > 0 && (
              <section className="space-y-3">
                <h2 className="text-lg font-semibold text-white">Decisions</h2>
                <ul className="space-y-2">
                  {report.decisions.map((decision, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm text-slate-300">
                      <span className="mt-1.5 shrink-0 size-2 rounded-full bg-blue-500" />
                      {decision}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Action Items */}
            <section className="space-y-3">
              <h2 className="text-lg font-semibold text-white">
                Action Items
                {actionItems.length > 0 && (
                  <span className="ml-2 text-xs text-slate-400 font-normal">
                    ({actionItems.length})
                  </span>
                )}
              </h2>
              {actionItems.length === 0 ? (
                <p className="text-sm text-slate-500">No action items recorded.</p>
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
              <h2 className="text-lg font-semibold text-white">Meeting Timeline</h2>
              <MeetingTimeline timeline={report.timeline ?? []} />
            </section>
          </div>

          {/* Right column — 1/3, sticky chat */}
          {isProcessed && (
            <div className="lg:col-span-1">
              <div className="lg:sticky lg:top-4">
                <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-slate-700/60">
                    <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-blue-500" />
                      Ask Arni
                    </h2>
                    <p className="text-xs text-slate-400 mt-0.5">About this meeting</p>
                  </div>
                  <QnAChat meetingId={meetingId!} token={token!} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
