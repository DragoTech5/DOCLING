/**
 * Admin Dashboard TypeScript Types
 * Interfaces for analytics data structures
 */

export interface OverviewStats {
  totalUsers: number
  totalUsersChange: number
  mrr: number
  mrrChange: number
  activeUsers: number
  activeUsersChange: number
  queriesToday: number
  queriesTodayChange: number
}

export interface RevenueData {
  date: string
  revenue: number
  newSubscriptions: number
  renewals: number
}

export interface TierData {
  tier: string
  count: number
  percentage: number
}

export interface FunnelStage {
  name: string
  count: number
  percentage: number
}

export interface UsageData {
  tier: string
  queries: number
}

export interface AdminUser {
  telegramId: number
  firstName: string
  username: string | null
  tier: string
  queriesUsed: number
  queriesRemaining: number
  subscriptionEndsAt: string | null
  createdAt: string
  lastActive: string | null
}

export interface AdminPaginationMeta {
  page: number
  perPage: number
  total: number
  totalPages: number
}

export interface AdminUsersResponse {
  users: AdminUser[]
  pagination: AdminPaginationMeta
}
