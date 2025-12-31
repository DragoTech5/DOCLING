import React from 'react'

interface StatsCardProps {
  title: string
  value: string | number
  change: number
  icon: React.ReactNode
  highlight?: boolean
}

export default function StatsCard({ title, value, change, icon, highlight = false }: StatsCardProps) {
  const isPositive = change >= 0
  const bgClass = highlight ? 'bg-cyan-900/20 border-cyan-700/30' : 'bg-black/20 border-gray-700/30'

  return (
    <div className={`group relative overflow-hidden rounded-lg border ${bgClass} p-4 backdrop-blur-sm transition-all hover:border-cyan-500/50 hover:bg-cyan-900/10`}>
      {/* Decorative gradient accent */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />

      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">{title}</p>
          <p className="mt-2 text-2xl font-bold text-white tabular-nums">{value}</p>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-400 transition-colors group-hover:bg-cyan-500/20">
          {icon}
        </div>
      </div>

      {/* Change indicator */}
      <div className="mt-3 flex items-center gap-1">
        {isPositive ? (
          <svg className="h-4 w-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M12 5a1 1 0 011.707-.707l2.828 2.829a1 1 0 11-1.414 1.414L13 7.414V15a1 1 0 11-2 0V7.414l-1.121 1.121a1 1 0 11-1.414-1.414l2.828-2.829A1 1 0 0112 5z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg className="h-4 w-4 text-red-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M12 15a1 1 0 01-1.707.707l-2.828-2.829a1 1 0 011.414-1.414L11 12.586V5a1 1 0 112 0v7.586l1.121-1.121a1 1 0 111.414 1.414l-2.828 2.829A1 1 0 0112 15z" clipRule="evenodd" />
          </svg>
        )}
        <span className={`text-sm font-semibold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
          {isPositive ? '+' : ''}{change}%
        </span>
        <span className="text-xs text-gray-500 ml-1">vs last month</span>
      </div>
    </div>
  )
}
