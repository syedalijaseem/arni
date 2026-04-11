import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

export default function ErrorPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const code = searchParams.get('code') ?? '404'
  const message = searchParams.get('message') ?? getDefaultMessage(code)

  function getDefaultMessage(statusCode: string): string {
    switch (statusCode) {
      case '403':
        return 'You do not have permission to view this page.'
      case '404':
        return 'The page you are looking for does not exist.'
      default:
        return 'Something went wrong. Please try again.'
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <Card className="p-10 max-w-sm w-full text-center space-y-6">
        <div className="space-y-2">
          <p className="text-5xl font-bold text-muted-foreground">{code}</p>
          <h1 className="text-lg font-semibold text-foreground">
            {code === '403' ? 'Access Denied' : 'Not Found'}
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">{message}</p>
        </div>
        <Button onClick={() => navigate('/dashboard')} className="w-full">
          Back to Dashboard
        </Button>
      </Card>
    </div>
  )
}
