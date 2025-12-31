import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChatStore } from '@/stores/chatStore'
import { hapticFeedback, showBackButton, hideBackButton, showConfirm } from '@/lib/telegram'
import BottomNav from '@/components/BottomNav'
import { clsx } from 'clsx'

export default function HistoryPage() {
  const navigate = useNavigate()
  const {
    conversations,
    isLoadingConversations,
    loadConversations,
    setCurrentConversation,
    deleteConversation,
    availablePdfs,
  } = useChatStore()

  // Setup back button
  useEffect(() => {
    showBackButton(() => {
      hapticFeedback('light')
      navigate('/')
    })
    return () => hideBackButton()
  }, [navigate])

  // Refresh conversations on mount
  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  const handleConversationClick = (conversation: typeof conversations[0]) => {
    hapticFeedback('light')
    setCurrentConversation(conversation)
    navigate(`/chat/${conversation.id}`)
  }

  const handleDelete = async (e: React.MouseEvent, conversationId: string) => {
    e.stopPropagation()
    hapticFeedback('warning')

    const confirmed = await showConfirm('Delete this conversation?')
    if (confirmed) {
      await deleteConversation(conversationId)
      hapticFeedback('success')
    }
  }

  const getPdfTitles = (pdfIds: string[]) => {
    return pdfIds
      .map(id => availablePdfs.find(pdf => pdf.id === id)?.title || 'Unknown')
      .slice(0, 2)
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return 'Today'
    if (days === 1) return 'Yesterday'
    if (days < 7) return `${days} days ago`
    return date.toLocaleDateString()
  }

  return (
    <div className="flex flex-col flex-1 pb-20">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-tg-header border-b border-tg-hint/20 px-4 py-3">
        <h1 className="text-lg font-semibold text-tg-text">Chat History</h1>
        <p className="text-xs text-tg-hint">{conversations.length} conversation{conversations.length !== 1 ? 's' : ''}</p>
      </header>

      {/* Content */}
      <main className="flex-1 px-4 py-4">
        {isLoadingConversations ? (
          <div className="flex items-center justify-center py-8">
            <div className="flex space-x-2">
              <div className="w-2 h-2 rounded-full bg-tg-button loading-dot"></div>
              <div className="w-2 h-2 rounded-full bg-tg-button loading-dot"></div>
              <div className="w-2 h-2 rounded-full bg-tg-button loading-dot"></div>
            </div>
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-12">
            <svg className="w-16 h-16 mx-auto text-tg-hint/50 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p className="text-tg-hint mb-4">No conversations yet</p>
            <button
              onClick={() => navigate('/')}
              className="bg-tg-button text-tg-button-text px-6 py-2 rounded-xl font-medium"
            >
              Start a chat
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {conversations.map((conversation) => {
              const pdfTitles = getPdfTitles(conversation.pdfIds)
              const lastMessage = conversation.messages[conversation.messages.length - 1]

              return (
                <button
                  key={conversation.id}
                  onClick={() => handleConversationClick(conversation)}
                  className={clsx(
                    'w-full bg-tg-secondary rounded-xl p-4 text-left transition-all',
                    'active:scale-[0.98]'
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-medium text-tg-text truncate">
                        {conversation.title || 'New Conversation'}
                      </h3>
                      <p className="text-xs text-tg-hint mt-0.5 truncate">
                        {pdfTitles.join(', ')}
                        {conversation.pdfIds.length > 2 && ` +${conversation.pdfIds.length - 2}`}
                      </p>
                      {lastMessage && (
                        <p className="text-xs text-tg-hint mt-1 line-clamp-2">
                          {lastMessage.role === 'user' ? 'You: ' : ''}
                          {lastMessage.content.slice(0, 100)}
                          {lastMessage.content.length > 100 && '...'}
                        </p>
                      )}
                    </div>

                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                      <span className="text-xs text-tg-hint">
                        {formatDate(conversation.updatedAt)}
                      </span>
                      <button
                        onClick={(e) => handleDelete(e, conversation.id)}
                        className="p-1.5 rounded-lg bg-tg-destructive/10 text-tg-destructive"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  {/* Message count badge */}
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-xs bg-tg-button/10 text-tg-button px-2 py-0.5 rounded-full">
                      {conversation.messages.length} message{conversation.messages.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </main>

      <BottomNav />
    </div>
  )
}
