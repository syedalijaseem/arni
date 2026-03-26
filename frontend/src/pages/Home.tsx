import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import ThemeToggle from '@/components/ThemeToggle'

interface HealthData {
  status: string
  app: string
  version: string
  database: string
}

function Home() {
  const { isAuthenticated } = useAuth()
  const [health, setHealth] = useState<HealthData | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <header className="flex items-center justify-between px-6 md:px-12 py-4 border-b">
        <span className="text-lg font-bold tracking-tight">Arni</span>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {isAuthenticated ? (
            <Button asChild>
              <Link to="/dashboard">Dashboard</Link>
            </Button>
          ) : (
            <>
              <Button variant="ghost" asChild>
                <Link to="/login">Sign in</Link>
              </Button>
              <Button asChild>
                <Link to="/register">Get started</Link>
              </Button>
            </>
          )}
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 py-24 md:py-32">
        <div className="inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium text-muted-foreground mb-6">
          AI Meeting Participant
        </div>

        <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-center max-w-3xl leading-[1.1]">
          Meet{' '}
          <span className="text-primary">Arni</span>
        </h1>

        <p className="mt-4 text-lg text-muted-foreground text-center max-w-xl leading-relaxed">
          Your AI teammate that joins meetings, listens, responds, and turns
          conversations into searchable knowledge.
        </p>

        <div className="flex gap-3 mt-8">
          {isAuthenticated ? (
            <Button size="lg" asChild>
              <Link to="/dashboard">Go to Dashboard</Link>
            </Button>
          ) : (
            <>
              <Button size="lg" asChild>
                <Link to="/register">Get started free</Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link to="/login">Sign in</Link>
              </Button>
            </>
          )}
        </div>

        {/* System status */}
        {health && (
          <Card className="mt-16 w-full max-w-sm">
            <CardContent className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                System Status
              </p>
              <div className="flex items-center justify-between text-sm">
                <span>API</span>
                <span className="flex items-center gap-1.5 text-emerald-500">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  Online
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span>Database</span>
                <span className="flex items-center gap-1.5 text-emerald-500">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  {health.database === 'connected' ? 'Connected' : 'Disconnected'}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span>Version</span>
                <span className="font-mono text-muted-foreground">{health.version}</span>
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  )
}

export default Home
