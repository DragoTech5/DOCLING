import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useAdminStore, initAdminAutoRefresh, cleanupAdminRefresh } from '@/stores/adminStore'
import { isAdminWhitelisted } from '@/config/features'
import StatsCard from '@/components/admin/StatsCard'
import RevenueChart from '@/components/admin/RevenueChart'
import TierDistributionChart from '@/components/admin/TierDistributionChart'
import ConversionFunnel from '@/components/admin/ConversionFunnel'
import UsageBarChart from '@/components/admin/UsageBarChart'
import UserTable from '@/components/admin/UserTable'
import BottomNav from '@/components/BottomNav'

// Icons for stats cards
const UsersIcon = () => (
  <svg fill="currentColor" viewBox="0 0 20 20" className="h-5 w-5">
    <path d="M10.5 1.5H5.75A2.25 2.25 0 003.5 3.75v12.5A2.25 2.25 0 005.75 18.5h8.5a2.25 2.25 0 002.25-2.25V10m-10-6h6m-6 3h6m-6 3h2" stroke="currentColor" strokeWidth="1.5" fill="none" />
  </svg>
)

const RevenueIcon = () => (
  <svg fill="currentColor" viewBox="0 0 20 20" className="h-5 w-5">
    <path fillRule="evenodd" d="M12 2a1 1 0 01.894.553l1.659 3.318a1 1 0 00.894.553h3.658a1 1 0 01.894 1.553l-2.963 2.712a1 1 0 00-.306 1.106l1.659 3.318a1 1 0 01-1.553 1.106L10 12.216l-2.963 2.712a1 1 0 01-1.553-1.106l1.659-3.318a1 1 0 00-.306-1.106L2.863 8.175a1 1 0 01.894-1.553h3.658a1 1 0 00.894-.553l1.659-3.318A1 1 0 0110 2z" clipRule="evenodd" />
  </svg>
)

const ActivityIcon = () => (
  <svg fill="currentColor" viewBox="0 0 20 20" className="h-5 w-5">
    <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
  </svg>
)

const QueryIcon = () => (
  <svg fill="currentColor" viewBox="0 0 20 20" className="h-5 w-5">
    <path fillRule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clipRule="evenodd" />
  </svg>
)

export default function AdminPage() {
  const navigate = useNavigate()
  const { telegramUser } = useAuthStore()
  const {
    overview,
    revenue,
    tierDistribution,
    conversionFunnel,
    usageByTier,
    users,
    usersPagination,
    isLoading,
    lastUpdated,
    autoRefresh,
    refreshAll,
    toggleAutoRefresh,
    setUserSearchQuery,
    setUserTierFilter,
    setUserSortBy,
    fetchUsers,
  } = useAdminStore()

  // Access control - redirect non-whitelisted users
  useEffect(() => {
    if (telegramUser && !isAdminWhitelisted(telegramUser.id)) {
      navigate('/', { replace: true })
    }
  }, [telegramUser, navigate])

  // Initialize data fetching
  useEffect(() => {
    refreshAll()
    initAdminAutoRefresh()

    // Cleanup on unmount
    return () => {
      cleanupAdminRefresh()
    }
  }, [refreshAll])

  // Format last updated time
  const getRelativeTime = (date: Date | null) => {
    if (!date) return 'Loading...'
    const now = new Date()
    const diff = Math.floor((now.getTime() - date.getTime()) / 1000)

    if (diff < 60) return 'Just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return date.toLocaleDateString()
  }

  if (!telegramUser || !isAdminWhitelisted(telegramUser.id)) {
    return null
  }

  return (
    <div className="flex flex-col flex-1 pb-20 bg-gradient-to-b from-gray-950 via-gray-900 to-black">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-gray-700/30 bg-black/40 backdrop-blur-md px-4 py-4 sm:px-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold bg-gradient-to-r from-cyan-400 via-cyan-300 to-cyan-400 bg-clip-text text-transparent">
              Admin Dashboard
            </h1>
            <p className="text-xs sm:text-sm text-gray-500 mt-1">
              Last updated: {getRelativeTime(lastUpdated)}
            </p>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => refreshAll()}
              disabled={isLoading}
              className="rounded-lg border border-gray-700/30 bg-black/20 px-3 py-2 text-sm font-medium text-gray-300 transition-all hover:border-cyan-500/50 hover:text-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Refresh data"
            >
              {isLoading ? (
                <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              ) : (
                '↻'
              )}
            </button>

            <button
              onClick={() => toggleAutoRefresh()}
              className={`rounded-lg px-3 py-2 text-xs font-medium transition-all ${
                autoRefresh
                  ? 'border border-cyan-500/50 bg-amber-900/20 text-cyan-400'
                  : 'border border-gray-700/30 bg-black/20 text-gray-300 hover:border-cyan-500/30'
              }`}
              title="Toggle auto-refresh (30s)"
            >
              {autoRefresh ? '🔄 Auto' : '⏸ Manual'}
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 px-4 py-6 sm:px-6 space-y-6 overflow-y-auto">
        {/* Overview Section */}
        <section className="space-y-4">
          <h2 className="text-xs sm:text-sm font-semibold text-cyan-400 uppercase tracking-widest">
            Overview
          </h2>
          {overview ? (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              <StatsCard
                title="Total Users"
                value={overview.totalUsers.toLocaleString()}
                change={overview.totalUsersChange}
                icon={<UsersIcon />}
                highlight
              />
              <StatsCard
                title="Monthly Revenue"
                value={`$${overview.mrr.toLocaleString()}`}
                change={overview.mrrChange}
                icon={<RevenueIcon />}
              />
              <StatsCard
                title="Active Users"
                value={overview.activeUsers.toLocaleString()}
                change={overview.activeUsersChange}
                icon={<ActivityIcon />}
              />
              <StatsCard
                title="Queries Today"
                value={overview.queriesToday.toLocaleString()}
                change={overview.queriesTodayChange}
                icon={<QueryIcon />}
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-32 rounded-lg border border-gray-700/30 bg-black/20 animate-pulse" />
              ))}
            </div>
          )}
        </section>

        {/* Charts Section */}
        <section className="space-y-4">
          <h2 className="text-xs sm:text-sm font-semibold text-cyan-400 uppercase tracking-widest">
            Analytics
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <RevenueChart data={revenue} />
            <TierDistributionChart data={tierDistribution} />
          </div>
        </section>

        {/* Metrics Section */}
        <section className="space-y-4">
          <h2 className="text-xs sm:text-sm font-semibold text-cyan-400 uppercase tracking-widest">
            Metrics
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ConversionFunnel stages={conversionFunnel} />
            <UsageBarChart data={usageByTier} />
          </div>
        </section>

        {/* Users Section */}
        <section className="space-y-4">
          <h2 className="text-xs sm:text-sm font-semibold text-cyan-400 uppercase tracking-widest">
            User Management
          </h2>
          <UserTable
            users={users}
            pagination={usersPagination}
            onSearch={setUserSearchQuery}
            onFilter={setUserTierFilter}
            onSort={setUserSortBy}
            onPageChange={(page) => fetchUsers(page)}
            isLoading={isLoading}
          />
        </section>
      </main>

      {/* Bottom Navigation */}
      <BottomNav />
    </div>
  )
}
