// Subscription tier types
export type SubscriptionTier = 'free' | 'starter' | 'pro' | 'unlimited' | 'enterprise' | 'scholar' | 'researcher'

export interface TierLimits {
  tier: SubscriptionTier
  maxPdfs: number | null // null = unlimited (document selections)
  dailyQueries: number | null // null = unlimited
  maxDownloads: number | null // null = unlimited (daily PDF downloads)
  maxCollections: number | null // null = unlimited
  historyDays: number | null // null = unlimited
  priceStars: number // in Telegram Stars
  priceUsd: number // in cents
}

export const TIER_LIMITS: Record<SubscriptionTier, TierLimits> = {
  free: { tier: 'free', maxPdfs: 1, dailyQueries: 6, maxDownloads: 1, maxCollections: 0, historyDays: 30, priceStars: 0, priceUsd: 0 },
  starter: { tier: 'starter', maxPdfs: null, dailyQueries: 25, maxDownloads: 3, maxCollections: null, historyDays: 90, priceStars: 430, priceUsd: 999 },
  pro: { tier: 'pro', maxPdfs: null, dailyQueries: 60, maxDownloads: 12, maxCollections: null, historyDays: 365, priceStars: 860, priceUsd: 1999 },
  unlimited: { tier: 'unlimited', maxPdfs: null, dailyQueries: null, maxDownloads: null, maxCollections: null, historyDays: null, priceStars: 2298, priceUsd: 4999 },
  enterprise: { tier: 'enterprise', maxPdfs: null, dailyQueries: null, maxDownloads: null, maxCollections: null, historyDays: null, priceStars: 2298, priceUsd: 4999 },
  // Legacy aliases for backwards compatibility
  scholar: { tier: 'starter', maxPdfs: null, dailyQueries: 25, maxDownloads: 3, maxCollections: null, historyDays: 90, priceStars: 430, priceUsd: 999 },
  researcher: { tier: 'pro', maxPdfs: null, dailyQueries: 60, maxDownloads: 12, maxCollections: null, historyDays: 365, priceStars: 860, priceUsd: 1999 },
}

// User types
export interface TelegramUser {
  id: number
  firstName: string
  lastName?: string
  username?: string
  languageCode?: string
  isPremium?: boolean
}

export interface UserProfile {
  telegramId: number
  tier: SubscriptionTier
  queriesUsed: number
  queriesRemaining: number
  subscriptionEndsAt?: string
  createdAt: string
}

// Chat types
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  timestamp: string
  isStreaming?: boolean
}

export interface Source {
  title: string
  source_url?: string  // URL if available
  source_type?: string  // e.g., "magick_pdf"
  channel_name?: string  // Author name
  published_date?: string
  document_id?: string  // For linking to book covers
  document_filename?: string  // For cover image lookup (filename without .pdf)
  // Legacy fields for backwards compatibility
  url?: string
  snippet?: string
  page?: number
}

export interface Conversation {
  id: string
  title: string
  pdfIds: string[]
  messages: Message[]
  createdAt: string
  updatedAt: string
}

// PDF types
export interface PDF {
  id: string
  title: string
  description?: string
  category: string
  pageCount?: number
  createdAt: string
}

// API response types
export interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
}

export interface ChatRequest {
  conversationId?: string
  message: string
  pdfIds: string[]
  collection: string
}

export interface ChatResponse {
  conversationId: string
  message: Message
}

export interface SubscriptionInvoice {
  invoiceUrl: string
}

export interface TokenBundle {
  id: string
  name: string
  tokens: number
  price: number // in Stars
}

export const TOKEN_BUNDLES: TokenBundle[] = [
  { id: 'bundle_small', name: '50 Queries', tokens: 50, price: 25 },
  { id: 'bundle_medium', name: '150 Queries', tokens: 150, price: 60 },
  { id: 'bundle_large', name: '500 Queries', tokens: 500, price: 175 },
]
