export default function LoadingScreen() {
  return (
    <div className="min-h-screen bg-dark flex flex-col items-center justify-center">
      {/* Golden glow orb */}
      <div className="relative mb-8">
        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-gold-400 to-gold-600 animate-pulse shadow-gold-glow-lg" />
        <div className="absolute inset-0 w-16 h-16 rounded-full bg-gold-500/30 animate-ping" />
      </div>

      {/* Loading dots */}
      <div className="flex space-x-3 mb-4">
        <div className="w-2 h-2 rounded-full bg-gold-400 loading-dot shadow-gold-glow-sm"></div>
        <div className="w-2 h-2 rounded-full bg-gold-400 loading-dot shadow-gold-glow-sm"></div>
        <div className="w-2 h-2 rounded-full bg-gold-400 loading-dot shadow-gold-glow-sm"></div>
      </div>

      {/* Title */}
      <h1 className="text-xl font-bold text-gold-400 text-glow mb-2">
        Knowledge Archive
      </h1>
      <p className="text-gray-500 text-sm">Unlocking ancient wisdom...</p>
    </div>
  )
}
