import { useState } from 'react'

interface ActionItem {
  id: string
  meeting_id: string
  description: string
  assignee: string | null
  deadline: string | null
  is_edited: boolean
  created_at: string
}

interface ActionItemCardProps {
  item: ActionItem
  onSave: (id: string, updates: Partial<Pick<ActionItem, 'description' | 'assignee' | 'deadline'>>) => Promise<void>
}

function ActionItemCard({ item, onSave }: ActionItemCardProps) {
  const [description, setDescription] = useState(item.description)
  const [assignee, setAssignee] = useState(item.assignee ?? '')
  const [deadline, setDeadline] = useState(item.deadline ?? '')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  async function handleSave(field: 'description' | 'assignee' | 'deadline') {
    const updates: Partial<Pick<ActionItem, 'description' | 'assignee' | 'deadline'>> = {}

    if (field === 'description') updates.description = description
    if (field === 'assignee') updates.assignee = assignee || null
    if (field === 'deadline') updates.deadline = deadline || null

    setIsSaving(true)
    setSaveError(null)
    try {
      await onSave(item.id, updates)
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <label className="text-xs text-muted-foreground mb-1 block">Description</label>
          <textarea
            className="w-full text-sm bg-background border border-input rounded px-2 py-1.5 resize-none focus:outline-none focus:ring-1 focus:ring-ring"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={() => handleSave('description')}
          />
        </div>
        {item.is_edited && (
          <span className="shrink-0 text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded-full">
            Edited
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Assignee</label>
          <input
            type="text"
            className="w-full text-sm bg-background border border-input rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="Unassigned"
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            onBlur={() => handleSave('assignee')}
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Deadline</label>
          <input
            type="text"
            className="w-full text-sm bg-background border border-input rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="No deadline"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
            onBlur={() => handleSave('deadline')}
          />
        </div>
      </div>

      {isSaving && (
        <p className="text-xs text-muted-foreground">Saving...</p>
      )}
      {saveError && (
        <p className="text-xs text-destructive">{saveError}</p>
      )}
    </div>
  )
}

export default ActionItemCard
