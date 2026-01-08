import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { hapticFeedback } from '@/lib/telegram'
import { SUPPORT_EMAIL, SUPPORT_EMAIL_URL } from '@/config/features'

export default function PaymentFailurePage() {
  const navigate = useNavigate()

  useEffect(() => {
    hapticFeedback('error')
  }, [])

  const handleRetry = () => {
    hapticFeedback('light')
    navigate('/pricing', { replace: true })
  }

  const handleHome = () => {
    hapticFeedback('light')
    navigate('/', { replace: true })
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-dark p-6">
      <div className="text-center space-y-4 max-w-sm">
        {/* Error icon */}
        <div className="flex justify-center">
          <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center">
            <svg className="w-8 h-8 text-red-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
          </div>
        </div>

        {/* Message */}
        <div>
          <h1 className="text-3xl font-bold text-red-400 mb-2">Payment Failed</h1>
          <p className="text-gray-400">
            Unfortunately, your payment could not be processed.
          </p>
        </div>

        {/* Details */}
        <div className="bg-dark-200 rounded-xl p-4 border border-red-500/20">
          <p className="text-sm text-gray-400">
            This could be due to:
          </p>
          <ul className="text-xs text-gray-500 mt-2 space-y-1">
            <li>• Card declined or expired</li>
            <li>• Insufficient funds</li>
            <li>• Network connection issue</li>
            <li>• Payment timeout</li>
          </ul>
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 pt-4">
          <button
            onClick={handleRetry}
            className="flex-1 py-3 rounded-xl font-semibold text-sm transition-all bg-gold-500 text-dark hover:bg-gold-400 active:scale-95"
          >
            Try Again
          </button>
          <button
            onClick={handleHome}
            className="flex-1 py-3 rounded-xl font-semibold text-sm transition-all bg-dark-400 text-gray-200 hover:bg-dark-300 active:scale-95"
          >
            Go Home
          </button>
        </div>

        {/* Support text */}
        <div className="text-xs text-gray-600 pt-4 space-y-2">
          <p>If the problem persists, try a different payment method.</p>
          <p>Need help? <a href={SUPPORT_EMAIL_URL} className="text-red-400 hover:text-red-300 underline font-medium">Contact support at {SUPPORT_EMAIL}</a></p>
        </div>
      </div>
    </div>
  )
}
