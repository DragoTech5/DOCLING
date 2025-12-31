import { useState } from 'react'
import { TierData } from '@/types/admin'

interface TierDistributionChartProps {
  data: TierData[]
}

const COLORS = {
  free: '#6B7280',
  starter: '#3B82F6',
  pro: '#8B5CF6',
  unlimited: '#FCD34D',
}

export default function TierDistributionChart({ data }: TierDistributionChartProps) {
  const [hoveredTier, setHoveredTier] = useState<string | null>(null)

  if (!data.length) {
    return (
      <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">
          User Distribution by Tier
        </h3>
        <div className="flex items-center justify-center h-64 text-gray-500">
          No data available
        </div>
      </div>
    )
  }

  const total = data.reduce((sum, d) => sum + d.count, 0)
  const radius = 60
  const centerX = 100
  const centerY = 100

  let startAngle = -Math.PI / 2
  const slices = data.map((item) => {
    const sliceAngle = (item.count / total) * 2 * Math.PI
    const endAngle = startAngle + sliceAngle
    const midAngle = startAngle + sliceAngle / 2

    // Label position
    const labelRadius = radius * 1.35
    const labelX = centerX + labelRadius * Math.cos(midAngle)
    const labelY = centerY + labelRadius * Math.sin(midAngle)

    // Arc path
    const x1 = centerX + radius * Math.cos(startAngle)
    const y1 = centerY + radius * Math.sin(startAngle)
    const x2 = centerX + radius * Math.cos(endAngle)
    const y2 = centerY + radius * Math.sin(endAngle)

    const largeArc = sliceAngle > Math.PI ? 1 : 0
    const pathData = `M ${centerX} ${centerY} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`

    const slice = {
      name: item.tier,
      count: item.count,
      percentage: item.percentage,
      pathData,
      labelX,
      labelY,
      color: COLORS[item.tier as keyof typeof COLORS] || '#9CA3AF',
      startAngle,
      endAngle,
    }

    startAngle = endAngle
    return slice
  })

  return (
    <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
      <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-6">
        User Distribution by Tier
      </h3>

      <div className="flex flex-col lg:flex-row items-center justify-center gap-8">
        <svg viewBox="0 0 240 240" className="w-48 h-48 lg:w-56 lg:h-56">
          {/* Pie slices */}
          {slices.map((slice) => (
            <g key={slice.name}>
              {/* Background circle for hover effect */}
              <circle
                cx={centerX}
                cy={centerY}
                r={radius + 5}
                fill="none"
                opacity={hoveredTier === slice.name ? 0.3 : 0}
                style={{ transition: 'opacity 0.2s' }}
              />

              {/* Slice */}
              <path
                d={slice.pathData}
                fill={slice.color}
                opacity={hoveredTier === null || hoveredTier === slice.name ? 1 : 0.4}
                onMouseEnter={() => setHoveredTier(slice.name)}
                onMouseLeave={() => setHoveredTier(null)}
                className="cursor-pointer transition-opacity duration-200"
                style={{
                  filter: hoveredTier === slice.name ? 'drop-shadow(0 0 8px rgba(252, 211, 77, 0.3))' : 'none',
                }}
              />

              {/* Percentage label */}
              <text
                x={slice.labelX}
                y={slice.labelY}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize="13"
                fontWeight="600"
                fill={slice.color}
                opacity={hoveredTier === null || hoveredTier === slice.name ? 1 : 0.5}
                pointerEvents="none"
                style={{ transition: 'opacity 0.2s' }}
              >
                {slice.percentage}%
              </text>
            </g>
          ))}
        </svg>

        {/* Legend */}
        <div className="space-y-3 flex-1">
          {slices.map((slice) => (
            <button
              key={slice.name}
              onMouseEnter={() => setHoveredTier(slice.name)}
              onMouseLeave={() => setHoveredTier(null)}
              className="w-full rounded-lg border border-gray-700/30 bg-black/20 p-3 text-left transition-all hover:border-cyan-500/50 hover:bg-black/40"
            >
              <div className="flex items-center gap-3">
                <div
                  className="h-3 w-3 rounded-full transition-all"
                  style={{
                    backgroundColor: slice.color,
                    boxShadow: hoveredTier === slice.name ? `0 0 8px ${slice.color}80` : 'none',
                  }}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-white capitalize">
                    {slice.name}
                  </p>
                  <p className="text-xs text-gray-400">
                    {slice.count.toLocaleString()} users
                  </p>
                </div>
                <p className="text-sm font-semibold text-gray-300 flex-shrink-0">
                  {slice.percentage}%
                </p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
