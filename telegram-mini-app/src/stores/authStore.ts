import { create } from 'zustand'
import type { TelegramUser, UserProfile, SubscriptionTier } from '@/types'
import { api } from '@/lib/api'
import { getTelegramUser, getInitData } from '@/lib/telegram'

interface AuthState {
  // State
  isInitialized: boolean
  isLoading: boolean
  error: string | null
  telegramUser: TelegramUser | null
  profile: UserProfile | null

  // Actions
  initialize: () => Promise<void>
  refreshProfile: () => Promise<void>
  updateTier: (tier: SubscriptionTier) => void
  deductQuery: () => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  isInitialized: false,
  isLoading: false,
  error: null,
  telegramUser: null,
  profile: null,

  initialize: async () => {
    if (get().isInitialized) return

    set({ isLoading: true, error: null })

    // Get Telegram user from WebApp
    const tgUser = getTelegramUser()
    if (tgUser) {
      set({
        telegramUser: {
          id: tgUser.id,
          firstName: tgUser.first_name,
          lastName: tgUser.last_name,
          username: tgUser.username,
          languageCode: tgUser.language_code,
          isPremium: tgUser.is_premium,
        },
      })
    }

    // Set init data for API authentication
    const initData = getInitData()
    api.setInitData(initData)

    // Always try to authenticate with backend (backend handles TWA_DEV_MODE)
    const result = await api.authenticate()
    if (result.success && result.data) {
      set({
        profile: result.data,
        isInitialized: true,
        isLoading: false,
      })
      return
    }

    // If auth fails but we have user data, continue with limited functionality
    if (result.error) {
      console.warn('Auth failed:', result.error)
    }

    // Default profile for when backend is unavailable
    set({
      profile: tgUser ? {
        telegramId: tgUser.id,
        tier: 'free',
        queriesUsed: 0,
        queriesRemaining: 20,
        createdAt: new Date().toISOString(),
      } : null,
      isInitialized: true,
      isLoading: false,
    })
  },

  refreshProfile: async () => {
    const result = await api.getProfile()
    if (result.success && result.data) {
      set({ profile: result.data })
    }
  },

  updateTier: (tier: SubscriptionTier) => {
    const profile = get().profile
    if (profile) {
      set({
        profile: { ...profile, tier },
      })
    }
  },

  deductQuery: () => {
    const profile = get().profile
    if (profile && profile.queriesRemaining > 0) {
      set({
        profile: {
          ...profile,
          queriesUsed: profile.queriesUsed + 1,
          queriesRemaining: profile.queriesRemaining - 1,
        },
      })
    }
  },
}))
