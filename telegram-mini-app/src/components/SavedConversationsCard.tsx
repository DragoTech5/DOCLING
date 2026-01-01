import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'

interface SavedConversation {
  id: string
  title: string
  createdAt: string
  messageCount: number
  docCount: number
}

export default function SavedConversationsCard() {
  const navigate = useNavigate()
  const { profile } = useAuthStore()
  const { loadFullConversation } = useChatStore()
  const [conversations, setConversations] = useState<SavedConversation[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fetch saved conversations
    const fetchConversations = async () => {
      try {
        setLoading(true)
        const response = await fetch('/api/telegram/saved-conversations', {
          headers: {
            'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || '',
          },
        })

        if (!response.ok) {
          if (response.status === 403) {
            // Free tier doesn't support saved conversations
            setConversations([])
            return
          }
          throw new Error(`Failed to fetch saved conversations: ${response.statusText}`)
        }

        const data = await response.json()
        // Show only the most recent 5 conversations
        setConversations(data.slice(0, 5))
      } catch (err) {
        console.error('Error fetching saved conversations:', err)
        setConversations([])
      } finally {
        setLoading(false)
      }
    }

    if (profile?.telegramId) {
      fetchConversations()
    }
  }, [profile?.telegramId])

  // Handle conversation click
  const handleConversationClick = async (savedConvId: string) => {
    try {
      // Load the full saved conversation
      const response = await fetch(
        `/api/telegram/saved-conversations/${savedConvId}`,
        {
          headers: {
            'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || '',
          },
        }
      )

      if (!response.ok) {
        throw new Error('Failed to load conversation')
      }

      const data = await response.json()

      // Load the conversation in the chat store (pass the conversation ID, not the entire object)
      await loadFullConversation(data.id)

      // Navigate to chat page
      navigate('/chat')
    } catch (err) {
      console.error('Error loading conversation:', err)
      alert('Failed to load conversation')
    }
  }

  // Free tier - no saved conversations
  if (profile?.tier === 'free') {
    return (
      <div className="relative overflow-hidden rounded-xl border border-cyan-500/20 bg-black/20 p-4 backdrop-blur-sm">
        <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 transition-opacity" />
        <h2 className="text-sm font-semibold text-cyan-400 mb-3">Saved Conversations</h2>
        <p className="text-xs text-gray-500 mb-3">
          Upgrade to Starter tier or higher to save and organize your conversations.
        </p>
        <button
          onClick={() => navigate('/pricing')}
          className="w-full bg-gradient-to-r from-cyan-600 to-cyan-500 rounded-lg py-2 text-center text-dark font-medium text-sm hover:from-cyan-500 hover:to-cyan-400 transition-all"
        >
          View Plans
        </button>
      </div>
    )
  }

  // Loading state
  if (loading) {
    return (
      <div className="relative overflow-hidden rounded-xl border border-cyan-500/20 bg-black/20 p-4 backdrop-blur-sm">
        <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 transition-opacity" />
        <h2 className="text-sm font-semibold text-cyan-400 mb-3">Saved Conversations</h2>
        <p className="text-xs text-gray-500">Loading...</p>
      </div>
    )
  }

  // Empty state
  if (conversations.length === 0) {
    return (
      <div className="relative overflow-hidden rounded-xl border border-cyan-500/20 bg-black/20 p-4 backdrop-blur-sm">
        <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 transition-opacity" />
        <h2 className="text-sm font-semibold text-cyan-400 mb-3">Saved Conversations</h2>
        <p className="text-xs text-gray-500">No saved conversations yet.</p>
        <p className="text-xs text-gray-600 mt-2">Start a chat and use the Save button to save conversations for later.</p>
      </div>
    )
  }

  // List conversations
  return (
    <div className="relative overflow-hidden rounded-xl border border-cyan-500/20 bg-black/20 p-4 backdrop-blur-sm">
      <div className="absolute inset-0 -z-10 bg-gradient-to-br from-cyan-500/5 to-transparent opacity-0 transition-opacity" />
      {/* Header with icon */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xl">💬</span>
        <div>
          <h2 className="text-sm font-semibold text-cyan-400 m-0">Saved Conversations</h2>
          <p className="text-xs text-gray-500 m-0 mt-0.5">
            {conversations.length} {conversations.length === 1 ? 'conversation' : 'conversations'}
          </p>
        </div>
      </div>

      {/* Conversations Grid */}
      <div className="space-y-2">
        {conversations.map((conv, idx) => {
          const createdDate = new Date(conv.createdAt)
          const dateStr =
            createdDate.toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
            })

          return (
            <button
              key={conv.id}
              onClick={() => handleConversationClick(conv.id)}
              className="w-full text-left group relative overflow-hidden"
              style={{
                animation: `slideInUp 0.3s ease-out ${idx * 50}ms both`
              }}
            >
              <style>{`
                @keyframes slideInUp {
                  from {
                    opacity: 0;
                    transform: translateY(8px);
                  }
                  to {
                    opacity: 1;
                    transform: translateY(0);
                  }
                }
              `}</style>

              {/* Background glow on hover */}
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/5 to-cyan-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-200" />

              <div className="relative rounded-xl p-4 border border-cyan-500/20 bg-dark-100 group-hover:border-cyan-500/50 group-hover:bg-dark-200 transition-all duration-200">
                {/* Title */}
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="text-sm font-medium text-gray-100 truncate flex-1 group-hover:text-cyan-400 transition-colors">
                    {conv.title}
                  </h3>
                  <span className="text-xs text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity">
                    →
                  </span>
                </div>

                {/* Meta info */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-3 text-xs">
                    <span className="text-gray-500">📅 {dateStr}</span>
                    <span className="text-gray-600">
                      💬 {conv.messageCount} msg{conv.messageCount !== 1 ? 's' : ''}
                    </span>
                  </div>
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* Empty state visual */}
      {conversations.length === 0 && (
        <div className="text-center py-6 text-gray-500">
          <p className="text-sm">No conversations yet</p>
          <p className="text-xs mt-1">Save your chats to keep them organized</p>
        </div>
      )}
    </div>
  )
}
