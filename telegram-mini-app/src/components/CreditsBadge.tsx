import { useAuthStore } from '@/stores/authStore'

export default function CreditsBadge() {
  const { profile } = useAuthStore()

  if (!profile) return null

  // Map tier to display name
  const getTierDisplayName = () => {
    if (profile.tier === 'unlimited' || profile.tier === 'enterprise') return 'Unlimited'
    if (profile.tier === 'pro') return 'Pro'
    if (profile.tier === 'starter') return 'Starter'
    return 'Free'
  }

  const tierName = getTierDisplayName()

  // Get tier-specific styling
  const getTierClass = () => {
    if (tierName === 'Unlimited') return 'tier-unlimited'
    if (tierName === 'Pro') return 'tier-pro'
    if (tierName === 'Starter') return 'tier-starter'
    return 'tier-free'
  }

  return (
    <div className="px-3 py-1.5 rounded-full text-sm font-semibold tier-badge">
      <span className={getTierClass()}>{tierName}</span>
    </div>
  )
}
