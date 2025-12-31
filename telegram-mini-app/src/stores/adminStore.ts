/**
 * Admin Dashboard Zustand Store
 * Manages analytics data state and auto-refresh logic
 */

import { create } from 'zustand'
import {
  OverviewStats,
  RevenueData,
  TierData,
  FunnelStage,
  UsageData,
  AdminUser,
  AdminUsersResponse,
  AdminPaginationMeta,
} from '@/types/admin'

interface AdminState {
  // Data
  overview: OverviewStats | null
  revenue: RevenueData[]
  tierDistribution: TierData[]
  conversionFunnel: FunnelStage[]
  usageByTier: UsageData[]
  users: AdminUser[]
  usersPagination: AdminPaginationMeta

  // UI State
  isLoading: boolean
  error: string | null
  lastUpdated: Date | null
  autoRefresh: boolean
  refreshInterval: NodeJS.Timeout | null

  // User filters
  userSearchQuery: string
  userTierFilter: string
  userSortBy: string

  // Fetch functions
  fetchOverview: () => Promise<void>
  fetchRevenue: (days?: number) => Promise<void>
  fetchTierDistribution: () => Promise<void>
  fetchConversionFunnel: () => Promise<void>
  fetchUsageByTier: () => Promise<void>
  fetchUsers: (page?: number, perPage?: number, search?: string, tier?: string, sort?: string) => Promise<void>

  // Control functions
  refreshAll: () => Promise<void>
  toggleAutoRefresh: () => void
  setUserSearchQuery: (query: string) => void
  setUserTierFilter: (tier: string) => void
  setUserSortBy: (sort: string) => void
}

const API_BASE = '/api/admin'

export const useAdminStore = create<AdminState>((set, get) => ({
  // Initial state
  overview: null,
  revenue: [],
  tierDistribution: [],
  conversionFunnel: [],
  usageByTier: [],
  users: [],
  usersPagination: { page: 1, perPage: 20, total: 0, totalPages: 0 },

  isLoading: false,
  error: null,
  lastUpdated: null,
  autoRefresh: true,
  refreshInterval: null,

  userSearchQuery: '',
  userTierFilter: '',
  userSortBy: 'created',

  // Fetch functions
  fetchOverview: async () => {
    try {
      const response = await fetch(`${API_BASE}/overview`)
      if (!response.ok) throw new Error('Failed to fetch overview')
      const data = await response.json()
      set({ overview: data, error: null })
    } catch (error) {
      set({ error: (error as Error).message })
    }
  },

  fetchRevenue: async (days = 30) => {
    try {
      const response = await fetch(`${API_BASE}/revenue?days=${days}`)
      if (!response.ok) throw new Error('Failed to fetch revenue')
      const data = await response.json()
      set({ revenue: data.data || [], error: null })
    } catch (error) {
      set({ error: (error as Error).message })
    }
  },

  fetchTierDistribution: async () => {
    try {
      const response = await fetch(`${API_BASE}/tier-distribution`)
      if (!response.ok) throw new Error('Failed to fetch tier distribution')
      const data = await response.json()
      set({ tierDistribution: data.data || [], error: null })
    } catch (error) {
      set({ error: (error as Error).message })
    }
  },

  fetchConversionFunnel: async () => {
    try {
      const response = await fetch(`${API_BASE}/conversion-funnel`)
      if (!response.ok) throw new Error('Failed to fetch conversion funnel')
      const data = await response.json()
      set({ conversionFunnel: data.data || [], error: null })
    } catch (error) {
      set({ error: (error as Error).message })
    }
  },

  fetchUsageByTier: async () => {
    try {
      const response = await fetch(`${API_BASE}/usage-by-tier`)
      if (!response.ok) throw new Error('Failed to fetch usage by tier')
      const data = await response.json()
      set({ usageByTier: data.data || [], error: null })
    } catch (error) {
      set({ error: (error as Error).message })
    }
  },

  fetchUsers: async (
    page = 1,
    perPage = 20,
    search = '',
    tier = '',
    sort = 'created'
  ) => {
    try {
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(perPage),
        search,
        tier,
        sort,
      })
      const response = await fetch(`${API_BASE}/users?${params}`)
      if (!response.ok) throw new Error('Failed to fetch users')
      const data: AdminUsersResponse = await response.json()
      set({
        users: data.users,
        usersPagination: data.pagination,
        error: null,
      })
    } catch (error) {
      set({ error: (error as Error).message })
    }
  },

  // Control functions
  refreshAll: async () => {
    set({ isLoading: true })
    try {
      const state = get()
      await Promise.all([
        state.fetchOverview(),
        state.fetchRevenue(),
        state.fetchTierDistribution(),
        state.fetchConversionFunnel(),
        state.fetchUsageByTier(),
        state.fetchUsers(
          state.usersPagination.page,
          state.usersPagination.perPage,
          state.userSearchQuery,
          state.userTierFilter,
          state.userSortBy
        ),
      ])
      set({ lastUpdated: new Date(), error: null })
    } catch (error) {
      set({ error: (error as Error).message })
    } finally {
      set({ isLoading: false })
    }
  },

  toggleAutoRefresh: () => {
    const state = get()
    set({ autoRefresh: !state.autoRefresh })

    // Clear existing interval if present
    if (state.refreshInterval) {
      clearInterval(state.refreshInterval)
    }

    // Set up new interval if toggled on
    if (!state.autoRefresh) {
      const interval = setInterval(() => {
        get().refreshAll()
      }, 30000) // 30 seconds
      set({ refreshInterval: interval })
    } else {
      set({ refreshInterval: null })
    }
  },

  setUserSearchQuery: (query: string) => {
    set({ userSearchQuery: query })
  },

  setUserTierFilter: (tier: string) => {
    set({ userTierFilter: tier })
  },

  setUserSortBy: (sort: string) => {
    set({ userSortBy: sort })
  },
}))

// Initialize auto-refresh on store creation
export const initAdminAutoRefresh = () => {
  const store = useAdminStore.getState()
  if (store.autoRefresh) {
    store.toggleAutoRefresh()
  }
}

// Cleanup function for component unmount
export const cleanupAdminRefresh = () => {
  const state = useAdminStore.getState()
  if (state.refreshInterval) {
    clearInterval(state.refreshInterval)
  }
}
