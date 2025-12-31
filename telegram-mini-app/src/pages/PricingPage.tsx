import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useSubscriptionStore } from '@/stores/subscriptionStore'
import { TIER_LIMITS, type SubscriptionTier } from '@/types'
import { hapticFeedback, showBackButton, hideBackButton, showAlert } from '@/lib/telegram'
import BottomNav from '@/components/BottomNav'
import { clsx } from 'clsx'
import { SHOW_DOCUMENT_LIMITS } from '@/config/features'

const tierOrder: SubscriptionTier[] = ['free', 'starter', 'pro', 'unlimited']

const tierDescriptions: Record<SubscriptionTier, string> = {
  free: 'Limited access to explore',
  starter: 'For regular researchers',
  pro: 'For power users',
  unlimited: 'Unlimited access to all wisdom',
  enterprise: 'Unlimited access to all wisdom',
  scholar: 'For regular researchers',  // Legacy alias
  researcher: 'For power users',  // Legacy alias
}

const tierColors: Record<SubscriptionTier, string> = {
  free: 'border-gray-500/20',
  starter: 'border-cyan-500/30',
  pro: 'border-cyan-500/35',
  unlimited: 'border-cyan-500/50',
  enterprise: 'border-cyan-500/50',
  scholar: 'border-cyan-500/30',  // Legacy alias
  researcher: 'border-cyan-500/35',  // Legacy alias
}

const paymentMethods: Record<SubscriptionTier, string | null> = {
  free: null,
  starter: 'Telegram Stars',
  pro: 'Telegram Stars',
  unlimited: 'Telegram Stars',
  enterprise: 'Telegram Stars',
  scholar: 'Telegram Stars',  // Legacy alias
  researcher: 'Telegram Stars',  // Legacy alias
}

export default function PricingPage() {
  const navigate = useNavigate()
  const { profile } = useAuthStore()
  const { subscribe, isProcessing } = useSubscriptionStore()

  const currentTier = profile?.tier || 'free'

  // Setup back button
  useEffect(() => {
    showBackButton(() => {
      hapticFeedback('light')
      navigate('/')
    })
    return () => hideBackButton()
  }, [navigate])

  const handleSubscribe = async (tier: SubscriptionTier) => {
    if (tier === currentTier || tier === 'free') return

    hapticFeedback('medium')
    const success = await subscribe(tier)

    if (success) {
      await showAlert('Subscription activated! Enjoy your new plan.')
      navigate('/')
    }
  }

  return (
    <div className="flex flex-col flex-1 pb-20 bg-dark">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-cyan-500/20 bg-black/40 backdrop-blur-sm px-4 py-4">
        <h1 className="text-xl font-bold text-cyan-300 text-glow">Choose Your Plan</h1>
        <p className="text-sm text-gray-500">Unlock deeper access to ancient wisdom</p>
      </header>

      {/* Content */}
      <main className="flex-1 px-4 py-4 space-y-4">
        {/* Subscription Plans */}
        {tierOrder.map((tier) => {
          const info = TIER_LIMITS[tier]
          const isCurrent = tier === currentTier
          const isUpgrade = tierOrder.indexOf(tier) > tierOrder.indexOf(currentTier)

          return (
            <div
              key={tier}
              className={clsx(
                'bg-dark-200 rounded-2xl p-4 border transition-all',
                tierColors[tier],
                isCurrent && 'ring-2 ring-cyan-500 shadow-lg',
                tier === 'unlimited' && 'relative overflow-hidden'
              )}
            >
              {/* Glow effect for unlimited tier */}
              {tier === 'unlimited' && (
                <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 to-transparent pointer-events-none" />
              )}

              <div className="relative">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className={clsx(
                        'text-lg font-bold capitalize',
                        tier === 'unlimited' ? 'text-cyan-300 text-glow' : 'text-gray-100'
                      )}>
                        {tier}
                      </h3>
                      {isCurrent && (
                        <span className="text-xs bg-cyan-500/20 text-cyan-400 px-2 py-0.5 rounded-full">
                          Current
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500">{tierDescriptions[tier]}</p>
                  </div>
                  <div className="text-right">
                    {info.priceUsd === 0 ? (
                      <p className="text-lg font-bold text-gray-300">Free</p>
                    ) : (
                      <>
                        <p className={clsx(
                          'text-2xl font-bold',
                          tier === 'unlimited' ? 'text-cyan-300' : 'text-gray-100'
                        )}>
                          ${info.priceUsd / 100}
                        </p>
                        <p className="text-xs text-gray-500">/month</p>
                      </>
                    )}
                    {paymentMethods[tier] && (
                      <p className="text-xs text-blue-400 mt-2 font-medium">
                        {paymentMethods[tier]}
                      </p>
                    )}
                  </div>
                </div>

                {/* Features */}
                <ul className="space-y-2 mb-4">
                  <li className="flex items-center gap-2 text-sm text-gray-300">
                    <svg className="w-4 h-4 text-cyan-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    <span>
                      {info.dailyQueries === null ? (
                        <strong className="text-cyan-400">Unlimited</strong>
                      ) : (
                        <>{info.dailyQueries}</>
                      )} questions/day
                    </span>
                  </li>
                  {SHOW_DOCUMENT_LIMITS && (
                    <li className="flex items-center gap-2 text-sm text-gray-300">
                      <svg className="w-4 h-4 text-cyan-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      <span>
                        {info.maxPdfs === null ? (
                          <strong className="text-cyan-400">Unlimited</strong>
                        ) : (
                          <>{info.maxPdfs}</>
                        )} document selections
                      </span>
                    </li>
                  )}
                  <li className="flex items-center gap-2 text-sm text-gray-300">
                    <svg className="w-4 h-4 text-cyan-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    <span>
                      {info.maxCollections === null ? (
                        <strong className="text-cyan-400">Unlimited</strong>
                      ) : info.maxCollections === 0 ? (
                        <span className="text-gray-500">No</span>
                      ) : (
                        <>{info.maxCollections}</>
                      )} saved collections
                    </span>
                  </li>
                  {info.historyDays && (
                    <li className="flex items-center gap-2 text-sm text-gray-300">
                      <svg className="w-4 h-4 text-cyan-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      <span>{info.historyDays}-day history</span>
                    </li>
                  )}
                  {info.historyDays === null && (
                    <li className="flex items-center gap-2 text-sm text-gray-300">
                      <svg className="w-4 h-4 text-cyan-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      <span><strong className="text-cyan-400">Unlimited</strong> history</span>
                    </li>
                  )}
                </ul>

                {/* Action button */}
                {isUpgrade && (
                  <button
                    onClick={() => handleSubscribe(tier)}
                    disabled={isProcessing}
                    className={clsx(
                      'w-full py-3 rounded-xl font-semibold text-sm transition-all',
                      tier === 'unlimited'
                        ? 'bg-cyan-500 text-dark btn-glow hover:bg-cyan-400'
                        : 'bg-dark-400 text-gray-200 hover:bg-dark-300',
                      isProcessing && 'opacity-50 cursor-not-allowed'
                    )}
                  >
                    {isProcessing ? 'Processing...' : tier === 'unlimited' ? 'Unlock Unlimited' : 'Subscribe'}
                  </button>
                )}
              </div>
            </div>
          )
        })}

        {/* Payment info */}
        <div className="bg-dark-200 rounded-xl p-4 border border-dark-400">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-5 h-5 text-cyan-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
            </svg>
            <h3 className="text-sm font-semibold text-gray-200">Payment Options</h3>
          </div>
          <p className="text-xs text-gray-500">
            Pay with Telegram Stars or credit card via Dodo Payments.
            Cancel anytime from your Telegram settings.
          </p>
        </div>

        {/* Current status */}
        {profile && (
          <div className="bg-dark-200 rounded-xl p-4 border border-dark-400">
            <h3 className="text-sm font-semibold text-cyan-400 mb-3">Your Current Usage</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Questions remaining today:</span>
                <span className="text-gray-200 font-medium">
                  {TIER_LIMITS[currentTier].dailyQueries === null
                    ? '∞'
                    : profile.queriesRemaining}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Current tier:</span>
                <span className="text-cyan-400 font-medium capitalize">{currentTier}</span>
              </div>
              {profile.subscriptionEndsAt && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Renews:</span>
                  <span className="text-gray-200">
                    {new Date(profile.subscriptionEndsAt).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      <BottomNav />
    </div>
  )
}
