import { useEffect } from 'react'
import type { SubscriptionTier } from '@/types'
import { TIER_LIMITS } from '@/types'
import { hapticFeedback, showBackButton, hideBackButton } from '@/lib/telegram'
import { clsx } from 'clsx'

interface PaymentMethodSelectorProps {
  tier: SubscriptionTier
  onSelectPaymentMethod: (method: 'telegram_stars' | 'dodo') => void
  onCancel: () => void
  isLoading?: boolean
}

export default function PaymentMethodSelector({
  tier,
  onSelectPaymentMethod,
  onCancel,
  isLoading = false,
}: PaymentMethodSelectorProps) {
  const tierInfo = TIER_LIMITS[tier]

  useEffect(() => {
    showBackButton(() => {
      hapticFeedback('light')
      onCancel()
    })
    return () => hideBackButton()
  }, [onCancel])

  const handleSelectMethod = (method: 'telegram_stars' | 'dodo') => {
    hapticFeedback('medium')
    onSelectPaymentMethod(method)
  }

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-dark-200 rounded-2xl border border-cyan-500/30 shadow-2xl max-w-sm w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 border-b border-cyan-500/20 bg-black/40 p-6">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-cyan-300 text-glow capitalize mb-2">
              {tier}
            </h2>
            <p className="text-gray-400">Choose your payment method</p>
          </div>
        </div>

        {/* Price Summary */}
        <div className="p-6 border-b border-cyan-500/10">
          <div className="bg-black/20 rounded-xl p-4">
            <div className="flex justify-between items-center mb-3">
              <span className="text-gray-300">Price per month:</span>
              <span className="text-2xl font-bold text-cyan-300">
                ${(tierInfo.priceUsd / 100).toFixed(2)}
              </span>
            </div>
            <div className="text-xs text-gray-500 pt-3 border-t border-cyan-500/10">
              <p>Includes:</p>
              <ul className="mt-2 space-y-1">
                <li>✓ {tierInfo.dailyQueries === null ? 'Unlimited' : tierInfo.dailyQueries} questions/day</li>
                {tierInfo.historyDays && (
                  <li>✓ {tierInfo.historyDays}-day history</li>
                )}
                {tierInfo.historyDays === null && (
                  <li>✓ Unlimited history</li>
                )}
              </ul>
            </div>
          </div>
        </div>

        {/* Payment Method Options */}
        <div className="p-6 space-y-4">
          {/* Telegram Stars Option */}
          <button
            onClick={() => handleSelectMethod('telegram_stars')}
            disabled={isLoading}
            className={clsx(
              'w-full p-4 rounded-xl border-2 transition-all text-left',
              'bg-black/20 border-cyan-500/30 hover:border-cyan-500/60 hover:bg-black/30',
              isLoading && 'opacity-50 cursor-not-allowed'
            )}
          >
            <div className="flex items-start gap-3">
              <div className="w-12 h-12 rounded-lg bg-cyan-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                <svg className="w-6 h-6 text-cyan-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4 4a2 2 0 00-2 2v4a2 2 0 002 2V6h10a2 2 0 00-2-2H4zm2 6a2 2 0 012-2h8a2 2 0 012 2v4a2 2 0 01-2 2H8a2 2 0 01-2-2v-4zm6 4a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-gray-100 mb-1">Telegram Stars</h3>
                <p className="text-sm text-gray-500">
                  Pay directly with Telegram Stars or convert from your Telegram wallet
                </p>
                <p className="text-xs text-cyan-400 mt-2 font-medium">
                  {tierInfo.priceStars} stars ≈ ${(tierInfo.priceUsd / 100).toFixed(2)}
                </p>
              </div>
            </div>
          </button>

          {/* Dodo Payments Option */}
          <button
            onClick={() => handleSelectMethod('dodo')}
            disabled={isLoading}
            className={clsx(
              'w-full p-4 rounded-xl border-2 transition-all text-left',
              'bg-black/20 border-cyan-500/30 hover:border-cyan-500/60 hover:bg-black/30',
              isLoading && 'opacity-50 cursor-not-allowed'
            )}
          >
            <div className="flex items-start gap-3">
              <div className="w-12 h-12 rounded-lg bg-cyan-500/20 flex items-center justify-center flex-shrink-0 mt-1">
                <svg className="w-6 h-6 text-cyan-400" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a1 1 0 110 2h-3a1 1 0 01-1-1v-2a1 1 0 00-1-1H9a1 1 0 00-1 1v2a1 1 0 01-1 1H4a1 1 0 110-2V4z" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-gray-100 mb-1">Credit Card</h3>
                <p className="text-sm text-gray-500">
                  Pay with Visa, Mastercard, or other payment methods via Dodo Payments
                </p>
                <p className="text-xs text-cyan-400 mt-2 font-medium">
                  ${(tierInfo.priceUsd / 100).toFixed(2)} per month
                </p>
              </div>
            </div>
          </button>
        </div>

        {/* Info Footer */}
        <div className="border-t border-cyan-500/10 p-4 bg-black/20">
          <p className="text-xs text-gray-500 text-center">
            Your subscription will renew automatically. You can cancel anytime.
          </p>
        </div>
      </div>
    </div>
  )
}
