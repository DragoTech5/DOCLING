import { create } from 'zustand'
import type { SubscriptionTier } from '@/types'
import { TIER_LIMITS, TOKEN_BUNDLES } from '@/types'
import { api } from '@/lib/api'
import { openInvoice, hapticFeedback } from '@/lib/telegram'
import { useAuthStore } from './authStore'

interface SubscriptionState {
  // State
  isProcessing: boolean
  lastPaymentStatus: 'paid' | 'cancelled' | 'failed' | 'pending' | null

  // Actions
  subscribe: (tier: SubscriptionTier, paymentMethod?: 'telegram_stars' | 'dodo') => Promise<boolean>
  purchaseTokens: (bundleId: string) => Promise<boolean>
  getTierInfo: (tier: SubscriptionTier) => typeof TIER_LIMITS[SubscriptionTier]
  canSelectMorePdfs: (currentCount: number) => boolean
  hasQueriesRemaining: () => boolean
}

export const useSubscriptionStore = create<SubscriptionState>((set) => ({
  isProcessing: false,
  lastPaymentStatus: null,

  subscribe: async (tier: SubscriptionTier, paymentMethod?: 'telegram_stars' | 'dodo') => {
    if (tier === 'free') return true

    set({ isProcessing: true })

    // Use provided payment method or auto-detect (default: Telegram Stars)
    const isDodoPayment = paymentMethod === 'dodo'

    try {
      if (isDodoPayment) {
        // Dodo Payments flow for credit card payments
        const initData = window.Telegram?.WebApp?.initData

        const response = await fetch('/api/payments/dodo/create-checkout', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Telegram-Init-Data': initData || '',
          },
          body: JSON.stringify({ tier }),
        })

        if (!response.ok) {
          const error = await response.json()
          console.error('Dodo checkout error:', error)
          set({ isProcessing: false, lastPaymentStatus: 'failed' })
          return false
        }

        const data = await response.json()

        // Open Dodo checkout in external link
        hapticFeedback('success')
        // Use @ts-ignore because openLink is a valid Telegram API method
        // @ts-ignore
        window.Telegram?.WebApp?.openLink(data.checkout_url)

        // Note: Return to this page via success/failure URLs handled by backend
        // User will be redirected to /payment-success or /payment-failure
        set({ isProcessing: false, lastPaymentStatus: 'pending' })
        return true
      } else {
        // Telegram Stars flow (default for all payment methods)
        const result = await api.createSubscriptionInvoice(tier)
        if (!result.success || !result.data?.invoiceUrl) {
          set({ isProcessing: false, lastPaymentStatus: 'failed' })
          return false
        }

        // Open Telegram's payment interface
        const status = await openInvoice(result.data.invoiceUrl)
        set({ isProcessing: false, lastPaymentStatus: status })

        if (status === 'paid') {
          // Payment successful - refresh profile
          hapticFeedback('success')
          await useAuthStore.getState().refreshProfile()
          return true
        }

        if (status === 'cancelled') {
          hapticFeedback('warning')
        } else {
          hapticFeedback('error')
        }

        return false
      }
    } catch (error) {
      console.error('Subscription error:', error)
      set({ isProcessing: false, lastPaymentStatus: 'failed' })
      hapticFeedback('error')
      return false
    }
  },

  purchaseTokens: async (bundleId: string) => {
    const bundle = TOKEN_BUNDLES.find(b => b.id === bundleId)
    if (!bundle) return false

    set({ isProcessing: true })

    const result = await api.purchaseTokenBundle(bundleId)
    if (!result.success || !result.data?.invoiceUrl) {
      set({ isProcessing: false, lastPaymentStatus: 'failed' })
      return false
    }

    // Open Telegram's payment interface
    const status = await openInvoice(result.data.invoiceUrl)
    set({ isProcessing: false, lastPaymentStatus: status })

    if (status === 'paid') {
      // Payment successful - refresh profile to get updated credits
      hapticFeedback('success')
      await useAuthStore.getState().refreshProfile()
      return true
    }

    if (status === 'cancelled') {
      hapticFeedback('warning')
    } else {
      hapticFeedback('error')
    }

    return false
  },

  getTierInfo: (tier: SubscriptionTier) => {
    return TIER_LIMITS[tier]
  },

  canSelectMorePdfs: (currentCount: number) => {
    const profile = useAuthStore.getState().profile
    if (!profile) return false

    const tierInfo = TIER_LIMITS[profile.tier]
    if (tierInfo.maxPdfs === null) return true // Unlimited
    return currentCount < tierInfo.maxPdfs
  },

  hasQueriesRemaining: () => {
    const profile = useAuthStore.getState().profile
    if (!profile) return false

    // Unlimited queries for enterprise and unlimited tiers
    if (profile.tier === 'enterprise' || profile.tier === 'unlimited') return true

    return profile.queriesRemaining > 0
  },
}))
