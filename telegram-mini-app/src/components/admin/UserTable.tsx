import { useState } from 'react'
import { AdminUser, AdminPaginationMeta } from '@/types/admin'

interface UserTableProps {
  users: AdminUser[]
  pagination: AdminPaginationMeta
  onSearch: (query: string) => void
  onFilter: (tier: string) => void
  onSort: (field: string) => void
  onPageChange: (page: number) => void
  isLoading?: boolean
}

const TIER_COLORS: Record<string, string> = {
  free: '#6B7280',
  starter: '#3B82F6',
  pro: '#8B5CF6',
  unlimited: '#FCD34D',
}

export default function UserTable({
  users,
  pagination,
  onSearch,
  onFilter,
  onSort,
  onPageChange,
  isLoading = false,
}: UserTableProps) {
  const [searchInput, setSearchInput] = useState('')
  const [selectedTier, setSelectedTier] = useState('')
  const [sortBy, setSortBy] = useState('created')
  const [hoveredUserId, setHoveredUserId] = useState<number | null>(null)

  const handleSearch = (value: string) => {
    setSearchInput(value)
    onSearch(value)
  }

  const handleFilter = (tier: string) => {
    setSelectedTier(tier)
    onFilter(tier)
  }

  const handleSort = (field: string) => {
    setSortBy(field)
    onSort(field)
  }

  if (isLoading && !users.length) {
    return (
      <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">Users</h3>
        <div className="flex items-center justify-center h-96 text-gray-500">
          <div className="text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400 mb-4" />
            <p>Loading users...</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-6">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Users ({pagination.total.toLocaleString()})
        </h3>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => handleSort('created')}
            className={`px-3 py-1 rounded text-xs font-semibold transition-all ${
              sortBy === 'created'
                ? 'bg-cyan-900/40 border border-cyan-500/50 text-cyan-400'
                : 'bg-black/40 border border-gray-700/30 text-gray-300 hover:border-cyan-500/30'
            }`}
          >
            Newest
          </button>
          <button
            onClick={() => handleSort('tier')}
            className={`px-3 py-1 rounded text-xs font-semibold transition-all ${
              sortBy === 'tier'
                ? 'bg-cyan-900/40 border border-cyan-500/50 text-cyan-400'
                : 'bg-black/40 border border-gray-700/30 text-gray-300 hover:border-cyan-500/30'
            }`}
          >
            Tier
          </button>
          <button
            onClick={() => handleSort('queries_used')}
            className={`px-3 py-1 rounded text-xs font-semibold transition-all ${
              sortBy === 'queries_used'
                ? 'bg-cyan-900/40 border border-cyan-500/50 text-cyan-400'
                : 'bg-black/40 border border-gray-700/30 text-gray-300 hover:border-cyan-500/30'
            }`}
          >
            Activity
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {/* Search */}
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search by name, username, or ID..."
            value={searchInput}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-700/30 bg-black/20 pl-10 pr-4 py-2 text-sm text-white placeholder-gray-500 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-colors"
          />
        </div>

        {/* Tier filter */}
        <select
          value={selectedTier}
          onChange={(e) => handleFilter(e.target.value)}
          className="rounded-lg border border-gray-700/30 bg-black/20 px-4 py-2 text-sm text-white focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-colors"
        >
          <option value="">All Tiers</option>
          <option value="free">Free</option>
          <option value="starter">Starter</option>
          <option value="pro">Pro</option>
          <option value="unlimited">Unlimited</option>
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700/30">
              <th className="px-4 py-3 text-left font-semibold text-gray-300 uppercase tracking-wider text-xs">User</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-300 uppercase tracking-wider text-xs">Tier</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-300 uppercase tracking-wider text-xs">Queries</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-300 uppercase tracking-wider text-xs">Expires</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-300 uppercase tracking-wider text-xs">Joined</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700/20">
            {users.map((user) => {
              const isHovered = hoveredUserId === user.telegramId
              const tierColor = TIER_COLORS[user.tier] || '#9CA3AF'

              return (
                <tr
                  key={user.telegramId}
                  onMouseEnter={() => setHoveredUserId(user.telegramId)}
                  onMouseLeave={() => setHoveredUserId(null)}
                  className={`transition-colors ${isHovered ? 'bg-cyan-900/10' : ''}`}
                >
                  {/* User info */}
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <p className="font-semibold text-white">{user.firstName}</p>
                      <p className="text-xs text-gray-500">
                        {user.username ? `@${user.username}` : `ID: ${user.telegramId}`}
                      </p>
                    </div>
                  </td>

                  {/* Tier */}
                  <td className="px-4 py-3">
                    <span
                      className="inline-block px-3 py-1 rounded-full text-xs font-semibold capitalize"
                      style={{
                        color: tierColor,
                        backgroundColor: `${tierColor}15`,
                        border: `1px solid ${tierColor}30`,
                      }}
                    >
                      {user.tier}
                    </span>
                  </td>

                  {/* Queries */}
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <p className="font-semibold text-white">{user.queriesUsed}</p>
                      <p className="text-xs text-gray-500">
                        {user.queriesRemaining >= 0
                          ? `${user.queriesRemaining} remaining`
                          : 'Unlimited'}
                      </p>
                    </div>
                  </td>

                  {/* Expiry */}
                  <td className="px-4 py-3">
                    {user.subscriptionEndsAt ? (
                      <p className="text-sm text-gray-300">
                        {new Date(user.subscriptionEndsAt).toLocaleDateString()}
                      </p>
                    ) : (
                      <p className="text-sm text-gray-500">-</p>
                    )}
                  </td>

                  {/* Joined */}
                  <td className="px-4 py-3">
                    <p className="text-sm text-gray-400">
                      {new Date(user.createdAt).toLocaleDateString()}
                    </p>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {!users.length && (
          <div className="flex items-center justify-center py-12 text-gray-500">
            No users found. Try adjusting your filters.
          </div>
        )}
      </div>

      {/* Pagination */}
      {pagination.totalPages > 1 && (
        <div className="mt-6 flex items-center justify-between border-t border-gray-700/30 pt-4">
          <p className="text-sm text-gray-400">
            Page {pagination.page} of {pagination.totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => onPageChange(Math.max(1, pagination.page - 1))}
              disabled={pagination.page === 1}
              className="rounded-lg border border-gray-700/30 bg-black/20 px-4 py-2 text-sm font-semibold text-gray-300 transition-all hover:border-cyan-500/50 hover:text-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              ← Previous
            </button>

            {/* Page numbers */}
            <div className="flex gap-1">
              {Array.from({ length: Math.min(5, pagination.totalPages) }, (_, i) => {
                const pageNum = pagination.page <= 3 ? i + 1 : pagination.page - 2 + i
                if (pageNum > pagination.totalPages) return null
                return (
                  <button
                    key={pageNum}
                    onClick={() => onPageChange(pageNum)}
                    className={`rounded-lg px-3 py-2 text-sm font-semibold transition-all ${
                      pageNum === pagination.page
                        ? 'bg-cyan-900/40 border border-cyan-500/50 text-cyan-400'
                        : 'border border-gray-700/30 bg-black/20 text-gray-300 hover:border-cyan-500/50'
                    }`}
                  >
                    {pageNum}
                  </button>
                )
              })}
            </div>

            <button
              onClick={() => onPageChange(Math.min(pagination.totalPages, pagination.page + 1))}
              disabled={pagination.page === pagination.totalPages}
              className="rounded-lg border border-gray-700/30 bg-black/20 px-4 py-2 text-sm font-semibold text-gray-300 transition-all hover:border-cyan-500/50 hover:text-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
