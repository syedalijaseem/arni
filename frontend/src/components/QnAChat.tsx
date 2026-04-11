import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface Source {
  chunk_index: number
  text: string
  score: number
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

interface QnAChatProps {
  meetingId: string
  token: string
}

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const RATE_LIMIT_MESSAGE =
  'You have reached the question limit for this meeting. Please try again later.'

export default function QnAChat({ meetingId, token }: QnAChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [rateLimited, setRateLimited] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const question = input.trim()
    if (!question || isSending || rateLimited) return

    const userMessage: Message = { role: 'user', content: question }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsSending(true)

    try {
      const resp = await fetch(`${API_BASE}/meetings/${meetingId}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question }),
      })

      if (resp.status === 429) {
        setRateLimited(true)
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: RATE_LIMIT_MESSAGE },
        ])
        return
      }

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        const detail = (body as { detail?: string }).detail ?? 'Failed to get answer.'
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: detail },
        ])
        return
      }

      const data = await resp.json()
      const assistantMessage: Message = {
        role: 'assistant',
        content: data.answer ?? 'No answer returned.',
        sources: data.sources ?? [],
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Network error. Please try again.' },
      ])
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="flex flex-col border border-border rounded-lg overflow-hidden bg-card">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[240px] max-h-[420px]">
        {messages.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center pt-8">
            Ask a question about this meeting.
          </p>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                }`}
              >
                {msg.content}
              </div>
              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <details className="text-xs text-muted-foreground max-w-[80%]">
                  <summary className="cursor-pointer select-none">
                    {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
                  </summary>
                  <ul className="mt-1 space-y-1 pl-2 border-l border-border">
                    {msg.sources.map((src) => (
                      <li key={src.chunk_index} className="line-clamp-2">
                        {src.text}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="flex gap-2 p-3 border-t border-border bg-background"
      >
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={rateLimited ? 'Question limit reached' : 'Ask about this meeting…'}
          disabled={isSending || rateLimited}
          className="flex-1"
        />
        <Button type="submit" disabled={isSending || rateLimited || !input.trim()}>
          {isSending ? 'Sending…' : 'Ask'}
        </Button>
      </form>
    </div>
  )
}
