import { useState } from 'react'
import { RevenueData } from '@/types/admin'

interface RevenueChartProps {
  data: RevenueData[]
}

export default function RevenueChart({ data }: RevenueChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)

  if (!data.length) {
    return (
      <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">
          Revenue Trend (30 Days)
        </h3>
        <div className="flex items-center justify-center h-64 text-gray-500">
          No data available
        </div>
      </div>
    )
  }

  // Calculate dimensions
  const maxRevenue = Math.max(...data.map(d => d.revenue), 1)
  const chartWidth = 320
  const chartHeight = 200
  const padding = { top: 20, right: 20, bottom: 30, left: 50 }

  const width = chartWidth - padding.left - padding.right
  const height = chartHeight - padding.top - padding.bottom

  // Calculate points for the path
  const points = data.map((point, i) => ({
    x: (i / (data.length - 1)) * width,
    y: height - (point.revenue / maxRevenue) * height,
    data: point,
  }))

  // Create smooth curve using cubic bezier
  const pathData = points
    .map((point, i) => {
      if (i === 0) return `M ${point.x} ${point.y}`

      const prev = points[i - 1]
      const controlX1 = prev.x + (point.x - prev.x) * 0.4
      const controlX2 = point.x - (point.x - prev.x) * 0.4

      return `C ${controlX1} ${prev.y}, ${controlX2} ${point.y}, ${point.x} ${point.y}`
    })
    .join(' ')

  // Create fill path
  const fillPath = `${pathData} L ${points[points.length - 1].x} ${height} L 0 ${height} Z`

  return (
    <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
      <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">
        Revenue Trend (30 Days)
      </h3>

      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-64">
        {/* Grid lines */}
        {[0, 1, 2, 3, 4].map((i) => (
          <line
            key={`grid-${i}`}
            x1={padding.left}
            y1={padding.top + (i / 4) * height}
            x2={chartWidth - padding.right}
            y2={padding.top + (i / 4) * height}
            stroke="#374151"
            strokeWidth="1"
            opacity="0.3"
            strokeDasharray="4"
          />
        ))}

        {/* Y-axis */}
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={chartHeight - padding.bottom} stroke="#4B5563" strokeWidth="1" />

        {/* X-axis */}
        <line x1={padding.left} y1={chartHeight - padding.bottom} x2={chartWidth - padding.right} y2={chartHeight - padding.bottom} stroke="#4B5563" strokeWidth="1" />

        {/* Fill area under curve */}
        <path d={fillPath} fill="url(#revenueGradient)" opacity="0.1" />

        {/* Revenue line */}
        <path d={pathData} fill="none" stroke="#FCD34D" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />

        {/* Gradient definition */}
        <defs>
          <linearGradient id="revenueGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#FCD34D" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#FCD34D" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Data points and hover zones */}
        {points.map((point, i) => (
          <g key={`point-${i}`}>
            {/* Invisible larger hover area */}
            <circle
              cx={padding.left + point.x}
              cy={padding.top + point.y}
              r="10"
              fill="transparent"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
              className="cursor-pointer"
            />

            {/* Visible point on hover */}
            {hoveredIndex === i && (
              <>
                <circle cx={padding.left + point.x} cy={padding.top + point.y} r="4" fill="#FCD34D" />
                <circle cx={padding.left + point.x} cy={padding.top + point.y} r="7" fill="none" stroke="#FCD34D" strokeWidth="1" opacity="0.4" />
              </>
            )}
          </g>
        ))}

        {/* Y-axis labels */}
        {[0, 1, 2, 3, 4].map((i) => (
          <text
            key={`y-label-${i}`}
            x={padding.left - 10}
            y={padding.top + (i / 4) * height + 4}
            textAnchor="end"
            fontSize="11"
            fill="#9CA3AF"
          >
            ${Math.round((maxRevenue * (4 - i)) / 4)}
          </text>
        ))}

        {/* X-axis labels (every 5 days) */}
        {data.map((d, i) => {
          if (i % 5 !== 0 && i !== data.length - 1) return null
          const x = (i / (data.length - 1)) * width
          return (
            <text
              key={`x-label-${i}`}
              x={padding.left + x}
              y={chartHeight - padding.bottom + 15}
              textAnchor="middle"
              fontSize="11"
              fill="#9CA3AF"
            >
              {d.date.slice(5)}
            </text>
          )
        })}

        {/* Hover tooltip */}
        {hoveredIndex !== null && (
          <g>
            <text
              x={chartWidth / 2}
              y={25}
              textAnchor="middle"
              fontSize="12"
              fill="#FCD34D"
              fontWeight="600"
            >
              ${points[hoveredIndex].data.revenue.toLocaleString()}
            </text>
            <text
              x={chartWidth / 2}
              y={40}
              textAnchor="middle"
              fontSize="10"
              fill="#9CA3AF"
            >
              {points[hoveredIndex].data.newSubscriptions} new • {points[hoveredIndex].data.renewals} renewals
            </text>
          </g>
        )}
      </svg>
    </div>
  )
}
