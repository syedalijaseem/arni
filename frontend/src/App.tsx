import { Suspense, lazy } from 'react'
import { Routes, Route } from 'react-router-dom'
import ProtectedRoute from '@/components/ProtectedRoute'
import { Card } from '@/components/ui/card'

const Home = lazy(() => import('@/pages/Home'))
const Login = lazy(() => import('@/pages/Login'))
const Register = lazy(() => import('@/pages/Register'))
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const MeetingRoom = lazy(() => import('@/pages/MeetingRoom'))
const PostMeetingReport = lazy(() => import('@/pages/PostMeetingReport'))
const ErrorPage = lazy(() => import('@/pages/ErrorPage'))

function RouteFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="p-8">
        <div className="text-sm text-muted-foreground">Loading page...</div>
      </Card>
    </div>
  )
}

function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/meeting/:inviteCode"
          element={
            <ProtectedRoute>
              <MeetingRoom />
            </ProtectedRoute>
          }
        />
        <Route
          path="/report/:meetingId"
          element={
            <ProtectedRoute>
              <PostMeetingReport />
            </ProtectedRoute>
          }
        />
        <Route path="/error" element={<ErrorPage />} />
      </Routes>
    </Suspense>
  )
}

export default App
