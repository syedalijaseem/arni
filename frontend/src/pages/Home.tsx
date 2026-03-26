import { useState, useEffect } from 'react'
import './Home.css'

interface HealthData {
  status: string
  app: string
  version: string
  database: string
}

function Home() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data: HealthData) => {
        setHealth(data)
        setLoading(false)
      })
      .catch(() => {
        setHealth({ status: 'unreachable', app: 'Arni', version: '—', database: 'unknown' })
        setLoading(false)
      })
  }, [])

  return (
    <div className="home">
      <div className="home__hero">
        <div className="home__badge">AI Meeting Participant</div>
        <h1 className="home__title">
          Meet <span className="home__title-accent">Arni</span>
        </h1>
        <p className="home__subtitle">
          Your AI teammate that joins meetings, listens, responds, and turns
          conversations into searchable knowledge.
        </p>

        <div className="home__status-card">
          <h3 className="home__status-title">System Status</h3>
          {loading ? (
            <div className="home__status-loading">
              <div className="home__spinner" />
              <span>Connecting...</span>
            </div>
          ) : (
            <div className="home__status-grid">
              <div className="home__status-item">
                <span className="home__status-label">API</span>
                <span
                  className={`home__status-value ${
                    health?.status === 'healthy'
                      ? 'home__status-value--ok'
                      : 'home__status-value--err'
                  }`}
                >
                  {health?.status === 'healthy' ? '● Online' : '● Offline'}
                </span>
              </div>
              <div className="home__status-item">
                <span className="home__status-label">Database</span>
                <span
                  className={`home__status-value ${
                    health?.database === 'connected'
                      ? 'home__status-value--ok'
                      : 'home__status-value--err'
                  }`}
                >
                  {health?.database === 'connected' ? '● Connected' : '● Disconnected'}
                </span>
              </div>
              <div className="home__status-item">
                <span className="home__status-label">Version</span>
                <span className="home__status-value">{health?.version || '—'}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Home
