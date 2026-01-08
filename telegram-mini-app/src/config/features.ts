/**
 * Feature flags for SaaS/Mini App
 * Centralized configuration for enabling/disabling features
 * Set ENABLE_MULTI_DOCUMENT_SELECTION to true to re-enable document selection feature
 */

// ========== FEATURE FLAGS ==========
/** Allow users to select specific documents for chatting (false = always chat with all docs) */
export const ENABLE_MULTI_DOCUMENT_SELECTION = false

/** Show document count limits in subscription plans */
export const SHOW_DOCUMENT_LIMITS = false

// ========== SUPPORT CONTACT INFORMATION ==========
/** Professional support email for customer inquiries */
export const SUPPORT_EMAIL = 'support@cyvril.com'

/** Support contact URL for mailto links */
export const SUPPORT_EMAIL_URL = `mailto:${SUPPORT_EMAIL}`

// ========== ADMIN ACCESS WHITELIST ==========
/** Telegram IDs of accounts with admin access via direct link */
export const ADMIN_WHITELIST = [
  1069852438,   // Ares Ariel (@Drakul55)
]

/**
 * Check if a Telegram user has admin access
 * @param telegramId - User's Telegram ID
 * @returns true if user is whitelisted for admin access
 */
export function isAdminWhitelisted(telegramId: number): boolean {
  return ADMIN_WHITELIST.includes(telegramId)
}
