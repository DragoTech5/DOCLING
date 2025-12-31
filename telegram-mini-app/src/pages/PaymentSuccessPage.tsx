import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { hapticFeedback } from '@/lib/telegram'

export default function PaymentSuccessPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const tier = searchParams.get('tier')
  const { refreshProfile } = useAuthStore()

  useEffect(() => {
    hapticFeedback('success')

    // Refresh user profile to get updated tier and subscription info
    const refreshAndRedirect = async () => {
      try {
        await refreshProfile()
      } catch (error) {
        console.error('Failed to refresh profile:', error)
      }

      // Redirect to home after 3 seconds
      const timer = setTimeout(() => {
        navigate('/', { replace: true })
      }, 3000)

      return () => clearTimeout(timer)
    }

    refreshAndRedirect()
  }, [navigate, refreshProfile])

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-dark p-6">
      <div className="text-center space-y-4">
        {/* Success icon */}
        <div className="flex justify-center">
          <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center animate-pulse">
            <svg className="w-8 h-8 text-green-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
          </div>
        </div>

        {/* Message */}
        <div>
          <h1 className="text-3xl font-bold text-green-400 mb-2">Payment Successful!</h1>
          <p className="text-gray-400">
            Your {tier} subscription is now active.
          </p>
        </div>

        {/* Status */}
        <div className="space-y-2">
          <p className="text-sm text-gray-500">
            Unlocking your new plan features...
          </p>
          <p className="text-xs text-gray-600">
            You'll be redirected to home in a moment
          </p>
        </div>

        {/* Loading indicator */}
        <div className="flex justify-center gap-1 pt-4">
          <div className="w-2 h-2 bg-gold-400 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
          <div className="w-2 h-2 bg-gold-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
          <div className="w-2 h-2 bg-gold-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
        </div>
      </div>
    </div>
  )
}
