import { useState } from 'react'
import { FunnelStage } from '@/types/admin'

interface ConversionFunnelProps {
  stages: FunnelStage[]
}

const STAGE_COLORS = {
  0: { main: '#3B82F6', accent: '#1E40AF' }, // Blue
  1: { main: '#8B5CF6', accent: '#5B21B6' }, // Purple
  2: { main: '#FCD34D', accent: '#B45309' }, // Gold
}

export default function ConversionFunnel({ stages }: ConversionFunnelProps) {
  const [hoveredStage, setHoveredStage] = useState<number | null>(null)

  if (!stages.length) {
    return (
      <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">
          Conversion Funnel
        </h3>
        <div className="flex items-center justify-center h-64 text-gray-500">
          No data available
        </div>
      </div>
    )
  }

  const chartWidth = 300
  const chartHeight = 240
  const topWidth = 200
  const bottomWidth = 60
  const stageHeight = 60
  const padding = 40

  return (
    <div className="rounded-lg border border-gray-700/30 bg-black/20 p-6 backdrop-blur-sm">
      <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-6">
        Conversion Funnel
      </h3>

      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-48 lg:h-56">
        {/* Funnel trapezoids */}
        {stages.map((stage, i) => {
          const widthAtStart = topWidth - (i * (topWidth - bottomWidth)) / stages.length
          const widthAtEnd = topWidth - ((i + 1) * (topWidth - bottomWidth)) / stages.length
          const yPos = padding / 2 + i * stageHeight

          // Trapezoid points
          const x1 = (chartWidth - widthAtStart) / 2
          const x2 = x1 + widthAtStart
          const x3 = (chartWidth - widthAtEnd) / 2 + widthAtEnd
          const x4 = (chartWidth - widthAtEnd) / 2
          const y1 = yPos
          const y2 = yPos + stageHeight - 8

          const pathData = `M ${x1} ${y1} L ${x2} ${y1} L ${x3} ${y2} L ${x4} ${y2} Z`
          const colors = STAGE_COLORS[i as keyof typeof STAGE_COLORS] || STAGE_COLORS[0]

          return (
            <g key={`stage-${i}`}>
              {/* Trapezoid */}
              <path
                d={pathData}
                fill={colors.main}
                opacity={hoveredStage === null || hoveredStage === i ? 0.8 : 0.3}
                onMouseEnter={() => setHoveredStage(i)}
                onMouseLeave={() => setHoveredStage(null)}
                className="cursor-pointer transition-opacity duration-200"
                style={{
                  filter: hoveredStage === i ? `drop-shadow(0 0 12px ${colors.main}40)` : 'none',
                }}
              />

              {/* Border */}
              <path
                d={pathData}
                fill="none"
                stroke={colors.main}
                strokeWidth="1.5"
                opacity={hoveredStage === null || hoveredStage === i ? 0.6 : 0.2}
                style={{ transition: 'opacity 0.2s' }}
              />

              {/* Stage content */}
              <g opacity={hoveredStage === null || hoveredStage === i ? 1 : 0.5} style={{ transition: 'opacity 0.2s' }}>
                {/* Count */}
                <text
                  x={chartWidth / 2}
                  y={yPos + 20}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize="14"
                  fontWeight="700"
                  fill="white"
                >
                  {stage.count.toLocaleString()}
                </text>

                {/* Conversion rate */}
                <text
                  x={chartWidth / 2}
                  y={yPos + 38}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize="11"
                  fill={colors.main}
                  fontWeight="600"
                >
                  {stage.percentage}% conversion
                </text>
              </g>
            </g>
          )
        })}

        {/* Conversion arrows/rates between stages */}
        {stages.slice(0, -1).map((_, i) => {
          const fromPercentage = stages[i].percentage
          const toPercentage = stages[i + 1].percentage
          const conversionRate = ((toPercentage / fromPercentage) * 100).toFixed(0)

          return (
            <text
              key={`arrow-${i}`}
              x={chartWidth / 2 + 60}
              y={padding / 2 + (i + 0.5) * stageHeight}
              fontSize="10"
              fill="#9CA3AF"
              textAnchor="start"
              dominantBaseline="middle"
            >
              ↓ {conversionRate}%
            </text>
          )
        })}
      </svg>

      {/* Stage labels below */}
      <div className="mt-4 flex justify-around gap-2">
        {stages.map((stage, i) => (
          <button
            key={`label-${i}`}
            onClick={() => setHoveredStage(hoveredStage === i ? null : i)}
            className={`rounded-lg border border-gray-700/30 px-3 py-2 text-center text-xs font-semibold transition-all ${
              hoveredStage === i
                ? 'border-cyan-500/50 bg-cyan-900/20'
                : 'bg-black/20 hover:border-cyan-500/30'
            }`}
          >
            <p className="capitalize text-white">{stage.name}</p>
            <p className="text-gray-400 text-xs mt-1">{stage.percentage}%</p>
          </button>
        ))}
      </div>
    </div>
  )
}
