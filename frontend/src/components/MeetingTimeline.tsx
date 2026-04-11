interface TimelineItem {
  timestamp: string
  topic: string
}

interface MeetingTimelineProps {
  timeline: TimelineItem[]
}

function MeetingTimeline({ timeline }: MeetingTimelineProps) {
  if (!timeline || timeline.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No timeline available.</p>
    )
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-[5.5rem] top-0 bottom-0 w-px bg-border" />

      <ul className="space-y-4">
        {timeline.map((item, index) => (
          <li key={index} className="flex gap-4 items-start">
            {/* Timestamp */}
            <span className="w-20 shrink-0 text-xs font-mono text-muted-foreground pt-0.5 text-right">
              {item.timestamp}
            </span>

            {/* Dot */}
            <div className="relative z-10 mt-1.5 shrink-0 size-2.5 rounded-full bg-primary border-2 border-background" />

            {/* Topic */}
            <span className="text-sm text-foreground">{item.topic}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default MeetingTimeline
