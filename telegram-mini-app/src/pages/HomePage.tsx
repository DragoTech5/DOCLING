import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import BottomNav from '@/components/BottomNav'
import SavedConversationsCard from '@/components/SavedConversationsCard'
import MysticalTeaserCard from '@/components/MysticalTeaserCard'

export default function HomePage() {
  const navigate = useNavigate()
  const { profile, telegramUser } = useAuthStore()

  // Get tier display info
  const getTierInfo = () => {
    const tier = profile?.tier
    if (tier === 'starter') return { name: 'Starter', dailyQueries: 33, selections: 6 }
    if (tier === 'pro') return { name: 'Pro', dailyQueries: 66, selections: 15 }
    if (tier === 'unlimited' || tier === 'enterprise') return { name: 'Unlimited', dailyQueries: '∞', selections: '∞' }
    return { name: 'Free', dailyQueries: 9, selections: 1 }
  }

  const tierInfo = getTierInfo()
  const queriesRemaining = profile?.queriesRemaining ?? 9
  const questionsUsedToday = (tierInfo.dailyQueries === '∞' ? 0 : (Number(tierInfo.dailyQueries) - queriesRemaining))

  return (
    <div className="flex flex-col flex-1 pb-20 bg-dark">
      {/* Header with cyan glow */}
      <header className="relative px-4 pt-8 pb-6 text-center">
        {/* Background glow effect */}
        <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/8 to-transparent pointer-events-none" />

        {/* Logo */}
        <div className="flex justify-center mb-4">
          <img
            src="/akasha-logo.png"
            alt="Akasha AI Logo"
            className="w-32 h-32 object-contain drop-shadow-lg opacity-95 hover:opacity-100 transition-opacity"
          />
        </div>

        <h1 className="text-3xl font-bold text-cyan-300 text-glow-strong mb-2">
          Akasha AI
        </h1>
        <p className="text-gray-400 text-sm">
          {telegramUser ? `Welcome, ${telegramUser.firstName}` : '9,078 Books and Documents'}
        </p>

        {/* Tier badge - shows only tier name */}
        <div className="mt-4 inline-flex items-center gap-2 px-5 py-2 rounded-full tier-badge">
          <svg className="w-4 h-4 text-cyan-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M5 2a2 2 0 00-2 2v14l3.5-2 3.5 2 3.5-2 3.5 2V4a2 2 0 00-2-2H5zm2.5 3a1.5 1.5 0 100 3 1.5 1.5 0 000-3zm6.207.293a1 1 0 00-1.414 0l-6 6a1 1 0 101.414 1.414l6-6a1 1 0 000-1.414zM12.5 10a1.5 1.5 0 100 3 1.5 1.5 0 000-3z" clipRule="evenodd" />
          </svg>
          <span className={`font-semibold ${
            tierInfo.name === 'Free' ? 'tier-free' :
            tierInfo.name === 'Starter' ? 'tier-starter' :
            tierInfo.name === 'Pro' ? 'tier-pro' : 'tier-unlimited'
          }`}>
            {tierInfo.name}
          </span>
        </div>
      </header>

      {/* Mystical Teaser Card - Marketing Hero */}
      <MysticalTeaserCard />

      {/* Main Content */}
      <main className="flex-1 px-4 py-4 space-y-4">
        {/* Quick Action Cards */}
        <div className="grid grid-cols-2 gap-3">
          {/* Browse Archive */}
          <button
            onClick={() => navigate('/archive')}
            className="group relative overflow-hidden rounded-2xl p-4 text-left border border-cyan-500/20 bg-black/20 backdrop-blur-sm hover:border-cyan-500/40 transition-all card-glow"
          >
            <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
            <div className="w-12 h-12 rounded-xl bg-cyan-500/15 flex items-center justify-center mb-3 group-hover:bg-cyan-500/25 transition-colors">
              <svg className="w-6 h-6 text-cyan-400" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
              </svg>
            </div>
            <h3 className="text-gray-100 font-semibold mb-1">Browse Archive</h3>
          </button>

          {/* Start Chat */}
          <button
            onClick={() => navigate('/chat')}
            className="group relative overflow-hidden rounded-2xl p-4 text-left border border-cyan-500/20 bg-black/20 backdrop-blur-sm hover:border-cyan-500/40 transition-all card-glow"
          >
            <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
            <div className="w-12 h-12 rounded-xl bg-cyan-500/15 flex items-center justify-center mb-3 group-hover:bg-cyan-500/25 transition-colors">
              <svg className="w-6 h-6 text-cyan-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clipRule="evenodd" />
              </svg>
            </div>
            <h3 className="text-gray-100 font-semibold mb-1">Start Chat</h3>
            <p className="text-xs text-gray-500">Ask the entire collection</p>
          </button>
        </div>

        {/* Saved Conversations Card */}
        <SavedConversationsCard />

        {/* Stats Section - Admin-style refined card */}
        <div className="relative overflow-hidden rounded-lg border border-cyan-500/20 bg-black/20 p-4 backdrop-blur-sm">
          <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 transition-opacity" />
          <h2 className="text-sm font-semibold text-cyan-400 mb-3 uppercase tracking-wider">Your Usage Today</h2>

          {/* Progress bar */}
          <div className="mb-4">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Questions</span>
              <span>
                {tierInfo.dailyQueries === '∞'
                  ? 'Unlimited'
                  : `${questionsUsedToday} / ${tierInfo.dailyQueries}`}
              </span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-cyan-500 to-cyan-400 rounded-full shadow-lg"
                style={{
                  width: tierInfo.dailyQueries === '∞'
                    ? '5%'
                    : `${Math.min((questionsUsedToday / Number(tierInfo.dailyQueries)) * 100, 100)}%`,
                  boxShadow: '0 0 12px rgba(6, 182, 212, 0.5)'
                }}
              />
            </div>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 gap-3">
            <div className="text-center">
              <p className="text-2xl font-bold text-cyan-300 text-glow tabular-nums">
                {typeof tierInfo.selections === 'number' ? tierInfo.selections : '∞'}
              </p>
              <p className="text-xs text-gray-500 mt-1">Doc Selections</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-cyan-300 text-glow tabular-nums">
                {queriesRemaining === 999999 ? '∞' : queriesRemaining}
              </p>
              <p className="text-xs text-gray-500 mt-1">Questions Left</p>
            </div>
          </div>
        </div>

        {/* Upgrade CTA (for free users) */}
        {profile?.tier === 'free' && (
          <button
            onClick={() => navigate('/pricing')}
            className="w-full group relative overflow-hidden rounded-2xl p-4 text-center btn-glow"
          >
            <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/30 to-cyan-600/20" />
            <p className="text-white font-bold text-lg">Unlock Full Access</p>
            <p className="text-cyan-200/70 text-sm">Get more questions, selections & collections</p>
          </button>
        )}
      </main>

      <BottomNav />
    </div>
  )
}
