import { useState } from 'react'
import { UsageData } from '@/types/admin'

interface UsageBarChartProps {
  data: UsageData[]
}

const TIER_COLORS: Record<string, string> = {
  free: '#6B7280',
  starter: '#3B82F6',
  pro: '#8B5CF6',
  unlimited: '#FCD34D',
}

export default function UsageBarChart({ data }: UsageBarChartProps) {
  const [hoveredTier, setHoveredTier] = useState<string | null>(null)

  if (!data.length) {
    return (
      <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">
          Query Volume by Tier
        </h3>
        <div className="flex items-center justify-center h-64 text-gray-500">
          No data available
        </div>
      </div>
    )
  }

  const maxQueries = Math.max(...data.map(d => d.queries), 1)

  return (
    <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
      <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-6">
        Query Volume by Tier
      </h3>

      <div className="space-y-6">
        {data.map((item, i) => {
          const percentage = (item.queries / maxQueries) * 100

          const color = TIER_COLORS[item.tier] || '#9CA3AF'
          const isHovered = hoveredTier === null || hoveredTier === item.tier

          return (
            <div
              key={`tier-${i}`}
              onMouseEnter={() => setHoveredTier(item.tier)}
              onMouseLeave={() => setHoveredTier(null)}
              className="group cursor-pointer"
            >
              {/* Label */}
              <div className="flex items-baseline justify-between mb-2">
                <p className={`text-sm font-semibold capitalize transition-colors ${isHovered ? 'text-white' : 'text-gray-400'}`}>
                  {item.tier}
                </p>
                <p className={`text-sm font-bold transition-colors ${isHovered ? 'text-cyan-400' : 'text-gray-500'}`}>
                  {item.queries.toLocaleString()} queries
                </p>
              </div>

              {/* Bar container */}
              <div className="h-8 w-full rounded-lg bg-gray-900/40 overflow-hidden border border-gray-800/50 group-hover:border-gray-700/50 transition-colors">
                {/* Gradient bar */}
                <div
                  style={{
                    width: `${percentage}%`,
                    backgroundColor: color,
                    height: '100%',
                    opacity: isHovered ? 1 : 0.6,
                    transition: 'all 0.2s ease-out',
                    boxShadow: isHovered ? `inset -2px 0 8px ${color}40, 0 0 12px ${color}40` : 'none',
                  }}
                  className="flex items-center justify-end pr-3 relative"
                >
                  {/* Percentage text inside bar if there's space */}
                  {percentage > 15 && (
                    <span className="text-xs font-bold text-gray-900" style={{ textShadow: '0 1px 2px rgba(0,0,0,0.2)' }}>
                      {Math.round(percentage)}%
                    </span>
                  )}
                </div>

                {/* Percentage text outside if bar is small */}
                {percentage <= 15 && (
                  <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2">
                    <span className="text-xs font-bold whitespace-nowrap" style={{ color }}>
                      {Math.round(percentage)}%
                    </span>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Summary stats */}
      <div className="mt-6 pt-6 border-t border-gray-700/30">
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg bg-black/20 p-3 border border-gray-700/30">
            <p className="text-xs text-gray-400 uppercase tracking-wide">Total Queries</p>
            <p className="mt-1 text-lg font-bold text-cyan-400">
              {data.reduce((sum, d) => sum + d.queries, 0).toLocaleString()}
            </p>
          </div>
          <div className="rounded-lg bg-black/20 p-3 border border-gray-700/30">
            <p className="text-xs text-gray-400 uppercase tracking-wide">Avg per Tier</p>
            <p className="mt-1 text-lg font-bold text-cyan-400">
              {Math.round(data.reduce((sum, d) => sum + d.queries, 0) / data.length).toLocaleString()}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
