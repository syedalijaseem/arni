import { useAuth } from '@/context/AuthContext'
import { Button } from '@/components/ui/button'
import ThemeToggle from '@/components/ThemeToggle'

function Dashboard() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-6 md:px-12 py-4 border-b bg-card">
        <span className="text-lg font-bold tracking-tight">
          <span className="text-primary">Arni</span>
        </span>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <span className="text-sm text-muted-foreground">
            {user?.name}
          </span>
          <Button variant="outline" size="sm" onClick={logout}>
            Sign out
          </Button>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6">
        <div className="text-center space-y-2">
          <h2 className="text-xl font-semibold">No meetings yet</h2>
          <p className="text-sm text-muted-foreground">
            Your meetings will appear here. Meeting creation is coming on Day 3.
          </p>
        </div>
      </main>
    </div>
  )
}

export default Dashboard
