import { useEffect, useState } from 'react'
import type { SubscriptionTier } from '@/types'
import { TIER_LIMITS } from '@/types'
import { hapticFeedback, showBackButton, hideBackButton } from '@/lib/telegram'
import { SUPPORT_EMAIL_URL } from '@/config/features'
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
  const [selectedMethod, setSelectedMethod] = useState<'telegram_stars' | 'dodo' | null>(null)
  const tierInfo = TIER_LIMITS[tier]

  useEffect(() => {
    showBackButton(() => {
      hapticFeedback('light')
      onCancel()
    })
    return () => hideBackButton()
  }, [onCancel])

  const handleSelectMethod = (method: 'telegram_stars' | 'dodo') => {
    hapticFeedback('light')
    setSelectedMethod(method)

    // Brief delay for visual feedback before proceeding
    setTimeout(() => {
      hapticFeedback('medium')
      onSelectPaymentMethod(method)
    }, 300)
  }

  return (
    <div className="fixed inset-0 bg-black/85 backdrop-blur-lg z-50 flex items-center justify-center p-4 animate-fade-in">
      {/* Decorative gradient orbs */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/5 rounded-full blur-3xl -z-10" />
      <div className="absolute bottom-0 left-0 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl -z-10" />

      <div className="bg-gradient-to-b from-slate-900/95 to-black/95 rounded-2xl border border-cyan-500/20 shadow-2xl max-w-sm w-full max-h-[90vh] overflow-y-auto backdrop-blur-xl animate-scale-in" style={{ animationDelay: '0.1s' }}>
        {/* Header Section */}
        <div className="relative border-b border-cyan-500/10 p-8 overflow-hidden">
          {/* Subtle gradient line */}
          <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-500/30 to-transparent" />

          <div className="text-center space-y-4">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-br from-cyan-500/30 to-blue-500/20 mb-2">
              <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>

            <div>
              <h2 className="text-2xl font-bold bg-gradient-to-r from-cyan-300 to-blue-300 bg-clip-text text-transparent capitalize mb-1">
                {tier} Plan
              </h2>
              <p className="text-sm text-gray-400">Select your payment method</p>
            </div>

            {/* Price Display */}
            <div className="pt-2">
              <div className="text-4xl font-bold text-white">
                ${(tierInfo.priceUsd / 100).toFixed(2)}
              </div>
              <p className="text-xs text-gray-500 mt-1">per month, cancel anytime</p>
            </div>
          </div>
        </div>

        {/* Features List */}
        <div className="px-8 py-6 border-b border-cyan-500/10 bg-black/30">
          <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider mb-3">What's Included</p>
          <ul className="space-y-2">
            <li className="flex items-center gap-2 text-sm text-gray-300">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
              {tierInfo.dailyQueries === null ? 'Unlimited' : tierInfo.dailyQueries} questions per day
            </li>
            <li className="flex items-center gap-2 text-sm text-gray-300">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
              {tierInfo.historyDays === null ? 'Unlimited' : tierInfo.historyDays}-day chat history
            </li>
            <li className="flex items-center gap-2 text-sm text-gray-300">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
              Priority support
            </li>
          </ul>
        </div>

        {/* Payment Methods */}
        <div className="p-8 space-y-4">
          <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider mb-6">Payment Method</p>

          {/* Telegram Stars Option */}
          <button
            onClick={() => handleSelectMethod('telegram_stars')}
            disabled={isLoading || selectedMethod !== null}
            className={clsx(
              'group relative w-full rounded-xl overflow-hidden transition-all duration-300',
              'border-2 p-5 text-left',
              selectedMethod === 'telegram_stars'
                ? 'border-cyan-500/60 bg-cyan-500/10'
                : 'border-cyan-500/20 hover:border-cyan-500/40 hover:bg-cyan-500/5 bg-black/40',
              (isLoading || selectedMethod !== null) && 'opacity-50 cursor-not-allowed'
            )}
          >
            {/* Selection indicator */}
            {selectedMethod === 'telegram_stars' && (
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 to-transparent animate-pulse" />
            )}

            <div className="relative flex items-start gap-4">
              <div className={clsx(
                'w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors duration-300',
                selectedMethod === 'telegram_stars'
                  ? 'bg-gradient-to-br from-cyan-500/40 to-blue-500/20'
                  : 'bg-cyan-500/15 group-hover:bg-cyan-500/25'
              )}>
                <svg className="w-6 h-6 text-cyan-300" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4 4a2 2 0 00-2 2v4a2 2 0 002 2V6h10a2 2 0 00-2-2H4zm2 6a2 2 0 012-2h8a2 2 0 012 2v4a2 2 0 01-2 2H8a2 2 0 01-2-2v-4zm6 4a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" />
                </svg>
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold text-gray-100">Telegram Stars</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 font-medium">
                    Instant
                  </span>
                </div>

                <p className="text-sm text-gray-400 mb-2">
                  Pay with native Telegram currency
                </p>

                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">
                    {tierInfo.priceStars} ⭐ stars
                  </span>
                  <span className="text-xs font-semibold text-cyan-300">
                    ${(tierInfo.priceUsd / 100).toFixed(2)}
                  </span>
                </div>
              </div>

              {selectedMethod === 'telegram_stars' && (
                <div className="flex-shrink-0 w-5 h-5 rounded-full border-2 border-cyan-400 flex items-center justify-center">
                  <div className="w-2 h-2 rounded-full bg-cyan-400" />
                </div>
              )}
            </div>
          </button>

          {/* Dodo Payments Option */}
          <button
            onClick={() => handleSelectMethod('dodo')}
            disabled={isLoading || selectedMethod !== null}
            className={clsx(
              'group relative w-full rounded-xl overflow-hidden transition-all duration-300',
              'border-2 p-5 text-left',
              selectedMethod === 'dodo'
                ? 'border-cyan-500/60 bg-cyan-500/10'
                : 'border-cyan-500/20 hover:border-cyan-500/40 hover:bg-cyan-500/5 bg-black/40',
              (isLoading || selectedMethod !== null) && 'opacity-50 cursor-not-allowed'
            )}
          >
            {/* Selection indicator */}
            {selectedMethod === 'dodo' && (
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 to-transparent animate-pulse" />
            )}

            <div className="relative flex items-start gap-4">
              <div className={clsx(
                'w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors duration-300',
                selectedMethod === 'dodo'
                  ? 'bg-gradient-to-br from-cyan-500/40 to-blue-500/20'
                  : 'bg-cyan-500/15 group-hover:bg-cyan-500/25'
              )}>
                <svg className="w-6 h-6 text-cyan-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h10m4 0a6 6 0 11-12 0 6 6 0 0112 0z" />
                </svg>
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold text-gray-100">Credit Card</h3>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-300 font-medium">
                    Recommended
                  </span>
                </div>

                <p className="text-sm text-gray-400 mb-2">
                  Visa, Mastercard & more via Dodo
                </p>

                <div className="flex items-center justify-between">
                  <div className="flex gap-1">
                    <span className="text-xs font-bold text-gray-400">💳</span>
                  </div>
                  <span className="text-xs font-semibold text-cyan-300">
                    ${(tierInfo.priceUsd / 100).toFixed(2)}
                  </span>
                </div>
              </div>

              {selectedMethod === 'dodo' && (
                <div className="flex-shrink-0 w-5 h-5 rounded-full border-2 border-cyan-400 flex items-center justify-center">
                  <div className="w-2 h-2 rounded-full bg-cyan-400" />
                </div>
              )}
            </div>
          </button>
        </div>

        {/* Security & Trust Footer */}
        <div className="px-8 py-6 border-t border-cyan-500/10 bg-black/50">
          <div className="flex items-center justify-center gap-4 text-xs text-gray-500 mb-4">
            <div className="flex items-center gap-1">
              <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 111.414 1.414L7.414 9l3.293 3.293a1 1 0 01-1.414 1.414l-4-4z" clipRule="evenodd" />
              </svg>
              Secure
            </div>
            <span>•</span>
            <div className="flex items-center gap-1">
              <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 111.414 1.414L7.414 9l3.293 3.293a1 1 0 01-1.414 1.414l-4-4z" clipRule="evenodd" />
              </svg>
              Encrypted
            </div>
            <span>•</span>
            <div className="flex items-center gap-1">
              <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 111.414 1.414L7.414 9l3.293 3.293a1 1 0 01-1.414 1.414l-4-4z" clipRule="evenodd" />
              </svg>
              PCI Compliant
            </div>
          </div>

          <p className="text-xs text-gray-500 text-center leading-relaxed mb-4">
            Your payment is processed securely. Subscription renews automatically—cancel anytime from your settings.
          </p>

          <div className="pt-3 border-t border-gray-800/30 text-center">
            <p className="text-xs text-gray-500">
              Questions?{' '}
              <a href={SUPPORT_EMAIL_URL} className="text-gray-400 hover:text-gray-300 underline transition-colors">
                contact support@cyvril.com
              </a>
            </p>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes fade-in {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        @keyframes scale-in {
          from {
            transform: scale(0.95);
            opacity: 0;
          }
          to {
            transform: scale(1);
            opacity: 1;
          }
        }

        .animate-fade-in {
          animation: fade-in 0.3s ease-out;
        }

        .animate-scale-in {
          animation: scale-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
      `}</style>
    </div>
  )
}
