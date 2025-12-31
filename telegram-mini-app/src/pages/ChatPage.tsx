import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { useChatStore } from '@/stores/chatStore'
import { useAuthStore } from '@/stores/authStore'
import { useSubscriptionStore } from '@/stores/subscriptionStore'
import { hapticFeedback, showBackButton, hideBackButton } from '@/lib/telegram'
import { clsx } from 'clsx'
import type { Source } from '@/types'
import { SelectedDocumentsDisplay } from '@/components/SelectedDocumentsDisplay'

// Save Conversation Modal Component - Enhanced UX
function SaveConversationModal({
  isOpen,
  onClose,
  onSave,
  conversationTitle,
  onTitleChange,
  isSaving,
  error,
}: {
  isOpen: boolean
  onClose: () => void
  onSave: () => Promise<void>
  conversationTitle: string
  onTitleChange: (title: string) => void
  isSaving: boolean
  error: string | null
}) {
  if (!isOpen) return null

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        backdropFilter: 'blur(4px)',
        animation: 'fadeIn 0.2s ease-out',
      }}
    >
      <style>{`
        @keyframes slideUp {
          from {
            transform: translateY(100%);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>

      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'linear-gradient(135deg, #1a1a24 0%, #1f1f2e 100%)',
          borderTop: '1px solid rgba(6, 182, 212, 0.2)',
          borderRadius: '28px 28px 0 0',
          padding: '32px 24px 28px',
          maxWidth: '100%',
          width: '100%',
          color: '#fff',
          animation: 'slideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
          maxHeight: '85vh',
          overflowY: 'auto',
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span style={{ fontSize: '20px' }}>💾</span>
            <h2 style={{ color: '#06B6D4', margin: 0, fontSize: '20px', fontWeight: '600' }}>
              Save This Conversation
            </h2>
          </div>
          <p style={{ margin: 0, fontSize: '13px', color: '#9ca3af', marginTop: '4px' }}>
            Give it a name to find it easily later
          </p>
        </div>

        {/* Error State */}
        {error && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            padding: '12px 14px',
            borderRadius: '10px',
            color: '#fca5a5',
            fontSize: '13px',
            marginBottom: '16px',
            display: 'flex',
            gap: '8px',
            alignItems: 'center'
          }}>
            <span>⚠️</span>
            {error}
          </div>
        )}

        {/* Title Input */}
        <div style={{ marginBottom: '20px' }}>
          <label style={{
            display: 'block',
            fontSize: '12px',
            fontWeight: '500',
            color: '#d1d5db',
            marginBottom: '8px',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}>
            Conversation Name
          </label>
          <input
            type="text"
            value={conversationTitle}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder="e.g., 'Knowledge on Archives'"
            disabled={isSaving}
            autoFocus
            style={{
              width: '100%',
              padding: '12px 14px',
              background: 'rgba(37, 37, 56, 0.8)',
              border: `2px solid ${conversationTitle.trim() ? '#06B6D4' : 'rgba(107, 114, 128, 0.3)'}`,
              borderRadius: '12px',
              color: '#fff',
              fontSize: '15px',
              boxSizing: 'border-box',
              outline: 'none',
              transition: 'border-color 0.2s',
              fontFamily: 'inherit'
            } as React.CSSProperties}
            onFocus={(e) => {
              (e.target as HTMLInputElement).style.borderColor = '#06B6D4'
            }}
            onBlur={(e) => {
              (e.target as HTMLInputElement).style.borderColor = conversationTitle.trim() ? '#06B6D4' : 'rgba(107, 114, 128, 0.3)'
            }}
          />
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={onClose}
            disabled={isSaving}
            style={{
              flex: 1,
              padding: '12px 16px',
              background: 'rgba(107, 114, 128, 0.1)',
              border: '1px solid rgba(107, 114, 128, 0.2)',
              borderRadius: '12px',
              color: '#e5e7eb',
              fontSize: '14px',
              fontWeight: '500',
              cursor: isSaving ? 'not-allowed' : 'pointer',
              opacity: isSaving ? 0.6 : 1,
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              if (!isSaving) {
                (e.target as HTMLButtonElement).style.background = 'rgba(107, 114, 128, 0.2)'
              }
            }}
            onMouseLeave={(e) => {
              (e.target as HTMLButtonElement).style.background = 'rgba(107, 114, 128, 0.1)'
            }}
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={!conversationTitle.trim() || isSaving}
            style={{
              flex: 1,
              padding: '12px 16px',
              background: !conversationTitle.trim() || isSaving ? 'rgba(6, 182, 212, 0.3)' : 'linear-gradient(135deg, #06B6D4 0%, #22d3ee 100%)',
              border: 'none',
              borderRadius: '12px',
              color: '#000',
              fontSize: '14px',
              fontWeight: '600',
              cursor: !conversationTitle.trim() || isSaving ? 'not-allowed' : 'pointer',
              opacity: !conversationTitle.trim() || isSaving ? 0.7 : 1,
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              if (conversationTitle.trim() && !isSaving) {
                (e.target as HTMLButtonElement).style.transform = 'translateY(-2px)'
                ;(e.target as HTMLButtonElement).style.boxShadow = '0 8px 16px rgba(212, 175, 55, 0.3)'
              }
            }}
            onMouseLeave={(e) => {
              (e.target as HTMLButtonElement).style.transform = 'translateY(0)'
              ;(e.target as HTMLButtonElement).style.boxShadow = 'none'
            }}
          >
            {isSaving ? (
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>⏳</span>
                Saving...
              </span>
            ) : (
              <>💾 Save Conversation</>
            )}
          </button>
        </div>

        <style>{`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    </div>,
    document.body
  )
}

// Share Conversation Modal Component - Enhanced UX
function ShareConversationModal({
  isOpen,
  onClose,
  shareUrl,
  isSharing,
  error,
}: {
  isOpen: boolean
  onClose: () => void
  shareUrl: string | null
  isSharing: boolean
  error: string | null
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    if (shareUrl) {
      navigator.clipboard.writeText(shareUrl).then(() => {
        setCopied(true)
        hapticFeedback('light')
        setTimeout(() => setCopied(false), 2000)
      })
    }
  }

  if (!isOpen) return null

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        backdropFilter: 'blur(4px)',
        animation: 'fadeIn 0.2s ease-out',
      }}
    >
      <style>{`
        @keyframes slideUp {
          from {
            transform: translateY(100%);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.8; }
        }
      `}</style>

      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'linear-gradient(135deg, #1a1a24 0%, #1f1f2e 100%)',
          borderTop: '1px solid rgba(6, 182, 212, 0.2)',
          borderRadius: '28px 28px 0 0',
          padding: '32px 24px 28px',
          maxWidth: '100%',
          width: '100%',
          color: '#fff',
          animation: 'slideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
          maxHeight: '85vh',
          overflowY: 'auto',
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span style={{ fontSize: '20px' }}>🔗</span>
            <h2 style={{ color: '#06B6D4', margin: 0, fontSize: '20px', fontWeight: '600' }}>
              Share This Conversation
            </h2>
          </div>
          <p style={{ margin: 0, fontSize: '13px', color: '#9ca3af', marginTop: '4px' }}>
            Anyone with the link can view this conversation
          </p>
        </div>

        {/* Error State */}
        {error && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            padding: '12px 14px',
            borderRadius: '10px',
            color: '#fca5a5',
            fontSize: '13px',
            marginBottom: '16px',
            display: 'flex',
            gap: '8px',
            alignItems: 'center'
          }}>
            <span>⚠️</span>
            {error}
          </div>
        )}

        {/* Loading State */}
        {isSharing && !shareUrl && (
          <div style={{
            background: 'rgba(59, 130, 246, 0.1)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            padding: '16px',
            borderRadius: '12px',
            textAlign: 'center',
            marginBottom: '20px'
          }}>
            <div style={{
              fontSize: '24px',
              marginBottom: '8px',
              animation: 'pulse 2s ease-in-out infinite'
            }}>⏳</div>
            <p style={{ margin: 0, fontSize: '13px', color: '#93c5fd' }}>
              Generating share link...
            </p>
          </div>
        )}

        {/* Share Link */}
        {shareUrl && (
          <div style={{ marginBottom: '24px' }}>
            <label style={{
              display: 'block',
              fontSize: '12px',
              fontWeight: '500',
              color: '#d1d5db',
              marginBottom: '10px',
              textTransform: 'uppercase',
              letterSpacing: '0.5px'
            }}>
              Share Link
            </label>
            <div style={{ display: 'flex', gap: '10px' }}>
              <div style={{
                flex: 1,
                padding: '12px 14px',
                background: 'rgba(37, 37, 56, 0.8)',
                border: '1px solid rgba(6, 182, 212, 0.2)',
                borderRadius: '12px',
                fontSize: '13px',
                color: '#9ca3af',
                wordBreak: 'break-all',
                display: 'flex',
                alignItems: 'center'
              }}>
                {shareUrl.split('/').pop()}
              </div>
              <button
                onClick={handleCopy}
                disabled={copied}
                style={{
                  padding: '12px 18px',
                  background: copied ? 'rgba(34, 197, 94, 0.2)' : 'linear-gradient(135deg, #06B6D4 0%, #22d3ee 100%)',
                  border: 'none',
                  borderRadius: '12px',
                  color: copied ? '#86efac' : '#000',
                  fontWeight: '600',
                  cursor: 'pointer',
                  fontSize: '13px',
                  transition: 'all 0.2s',
                  whiteSpace: 'nowrap',
                  minWidth: 'fit-content'
                }}
                onMouseEnter={(e) => {
                  if (!copied) {
                    (e.target as HTMLButtonElement).style.transform = 'translateY(-2px)'
                    ;(e.target as HTMLButtonElement).style.boxShadow = '0 8px 16px rgba(212, 175, 55, 0.3)'
                  }
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLButtonElement).style.transform = 'translateY(0)'
                  ;(e.target as HTMLButtonElement).style.boxShadow = 'none'
                }}
              >
                {copied ? '✓ Copied!' : '📋 Copy'}
              </button>
            </div>

            {/* Info Box */}
            <div style={{
              marginTop: '14px',
              padding: '12px',
              background: 'rgba(6, 182, 212, 0.05)',
              border: '1px solid rgba(6, 182, 212, 0.1)',
              borderRadius: '10px',
              fontSize: '12px',
              color: '#d1d5db',
              display: 'flex',
              gap: '8px'
            }}>
              <span>ℹ️</span>
              <span>This link is public. Anyone with it can read this conversation without logging in.</span>
            </div>
          </div>
        )}

        {/* Action Button */}
        <button
          onClick={onClose}
          disabled={isSharing}
          style={{
            width: '100%',
            padding: '12px 16px',
            background: 'rgba(107, 114, 128, 0.1)',
            border: '1px solid rgba(107, 114, 128, 0.2)',
            borderRadius: '12px',
            color: '#e5e7eb',
            fontSize: '14px',
            fontWeight: '500',
            cursor: isSharing ? 'not-allowed' : 'pointer',
            opacity: isSharing ? 0.6 : 1,
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            if (!isSharing) {
              (e.target as HTMLButtonElement).style.background = 'rgba(107, 114, 128, 0.2)'
            }
          }}
          onMouseLeave={(e) => {
            (e.target as HTMLButtonElement).style.background = 'rgba(107, 114, 128, 0.1)'
          }}
        >
          {isSharing ? 'Creating share link...' : 'Done'}
        </button>
      </div>
    </div>,
    document.body
  )
}

// Helper to get cover URL for a source
function getCoverUrl(source: Source): string | null {
  // Use document_filename for cover lookup (covers are named by PDF filename)
  if (source.document_filename) {
    return `/covers/maglib/${encodeURIComponent(source.document_filename)}.jpg`
  }
  return null
}

export default function ChatPage() {
  const { conversationId } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [initialized, setInitialized] = useState(false)
  const [chatWithAll, setChatWithAll] = useState(false)
  const [selectedSource, setSelectedSource] = useState<Source | null>(null) // For thumbnail modal
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [saveTitle, setSaveTitle] = useState('')
  const [isSavingConversation, setIsSavingConversation] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setShowSuccess] = useState(false)
  const [showShareModal, setShowShareModal] = useState(false)
  const [shareUrl, setShareUrl] = useState<string | null>(null)
  const [isSharing, setIsSharing] = useState(false)
  const [shareError, setShareError] = useState<string | null>(null)
  const [isDocumentsExpanded, setIsDocumentsExpanded] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const {
    currentConversation,
    setCurrentConversation,
    sendMessage,
    isSending,
    availablePdfs,
    selectedPdfIds,
    setSelectedPdfIds,
    loadFullConversation,
    loadPdfs,
    isLoadingPdfs,
  } = useChatStore()
  const { deductQuery, profile } = useAuthStore()
  const { hasQueriesRemaining } = useSubscriptionStore()

  // Handle saving conversation
  const handleSaveConversation = async () => {
    if (!currentConversation?.messages || currentConversation.messages.length === 0) {
      setSaveError('No messages to save')
      return
    }

    // Check if we have a valid conversation ID
    if (!currentConversation.id || currentConversation.id.startsWith('new-')) {
      setSaveError('Please send at least one message first')
      return
    }

    // Check tier limits
    const tier = profile?.tier
    if (tier === 'free') {
      setSaveError('Upgrade to Starter tier or higher to save conversations')
      setShowSaveModal(false)
      return
    }

    // Auto-generate title if not provided
    const title = saveTitle.trim() || (currentConversation.messages[0]?.content?.slice(0, 50) + '...' || 'Untitled Chat')

    try {
      setIsSavingConversation(true)
      setSaveError(null)

      const response = await fetch('/api/telegram/saved-conversations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Telegram-Init-Data': `user=${profile?.telegramId}`,
        },
        body: JSON.stringify({
          conversationId: currentConversation.id,
          title,
          selectedDocIds: selectedPdfIds,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        if (response.status === 403) {
          setSaveError('Upgrade to Starter tier or higher to save conversations')
        } else if (response.status === 429) {
          setSaveError('Reached save limit for your tier')
        } else {
          setSaveError(errorData.detail || 'Failed to save conversation')
        }
        return
      }

      // Parse response to get the saved conversation ID
      const savedData = await response.json()
      console.log('💾 Conversation saved with ID:', savedData.id)

      // Update currentConversation with the new ID so sharing works
      if (currentConversation) {
        setCurrentConversation({
          ...currentConversation,
          id: savedData.id  // Replace 'new-' ID with actual saved ID
        })
      }

      // Show success message
      hapticFeedback('success')
      setShowSuccess(true)
      setShowSaveModal(false)
      setSaveTitle('')

      // Hide success message after 2 seconds
      setTimeout(() => setShowSuccess(false), 2000)
    } catch (err) {
      console.error('Error saving conversation:', err)
      setSaveError('Failed to save conversation')
    } finally {
      setIsSavingConversation(false)
    }
  }

  // Handle sharing conversation
  const handleShareConversation = async () => {
    if (!currentConversation?.id || !currentConversation.messages || currentConversation.messages.length === 0) {
      setShareError('No messages to share')
      return
    }

    try {
      setIsSharing(true)
      setShareError(null)
      setShareUrl(null)

      // If conversation is unsaved (starts with 'new-'), save it first
      let conversationIdToShare = currentConversation.id
      if (currentConversation.id.startsWith('new-')) {
        console.log('Conversation unsaved, auto-saving before sharing...')
        const title = currentConversation.messages[0]?.content?.slice(0, 50) + '...' || 'Untitled Chat'
        const saveResponse = await fetch('/api/telegram/saved-conversations', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Telegram-Init-Data': `user=${profile?.telegramId}`,
          },
          body: JSON.stringify({
            conversationId: currentConversation.id,
            title,
            selectedDocIds: selectedPdfIds,
          }),
        })

        if (!saveResponse.ok) {
          const errorData = await saveResponse.json()
          setShareError(errorData.detail || 'Failed to save conversation before sharing')
          return
        }

        const savedData = await saveResponse.json()
        conversationIdToShare = savedData.id
        // Update conversation ID so subsequent operations use the saved ID
        setCurrentConversation({
          ...currentConversation,
          id: conversationIdToShare,
        })
      }

      // Now share the conversation (saved or already was saved)
      const response = await fetch(`/api/telegram/saved-conversations/${conversationIdToShare}/share`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Telegram-Init-Data': `user=${profile?.telegramId}`,
        },
      })

      if (!response.ok) {
        const errorData = await response.json()
        if (response.status === 404) {
          setShareError('Conversation not found. Please save it first.')
        } else {
          setShareError(errorData.detail || 'Failed to share conversation')
        }
        return
      }

      const data = await response.json()
      const url = data.shareUrl
      setShareUrl(url)
      hapticFeedback('success')
    } catch (err) {
      console.error('Error sharing conversation:', err)
      setShareError('Failed to share conversation')
    } finally {
      setIsSharing(false)
    }
  }

  // Initialize from URL params on mount
  useEffect(() => {
    const docsParam = searchParams.get('docs')

    // Only handle docs param if no conversationId is provided
    // If conversationId exists, loadFullConversation will load the conversation's documents
    if (conversationId) {
      if (!initialized) {
        setInitialized(true)
      }
      return
    }

    // Parse docs from URL: ?docs=maglib:123,bibliothek:456 or ?docs=all
    if (docsParam) {
      if (docsParam === 'all') {
        // Chat with all documents - don't set specific IDs
        setChatWithAll(true)
        setSelectedPdfIds([]) // Empty means all
        setCurrentConversation({
          id: `new-${Date.now()}`,
          title: 'Chat with All Documents',
          messages: [],
          pdfIds: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        })
      } else {
        const docIds = docsParam.split(',').filter(Boolean)
        if (docIds.length > 0) {
          setSelectedPdfIds(docIds)
          // Create a new empty conversation for this chat
          setCurrentConversation({
            id: `new-${Date.now()}`,
            title: 'New Chat',
            messages: [],
            pdfIds: docIds,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          })
        }
      }
    } else {
      // Default to Chat with All Documents when no docs param provided
      setChatWithAll(true)
      setSelectedPdfIds([])
      setCurrentConversation({
        id: `new-${Date.now()}`,
        title: 'Chat with All Documents',
        messages: [],
        pdfIds: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })
    }

    if (!initialized) {
      setInitialized(true)
    }
  }, [searchParams, conversationId, setSelectedPdfIds, setCurrentConversation])

  // Load conversation if ID provided
  useEffect(() => {
    if (conversationId) {
      // Load full conversation with messages from backend
      loadFullConversation(conversationId)
    }
  }, [conversationId, loadFullConversation])

  // Load available documents for SelectedDocumentsDisplay component
  // This MUST be called so that selectedPdfIds can be matched against availablePdfs
  useEffect(() => {
    console.log('🔌 ChatPage useEffect: calling loadPdfs()')
    ;(async () => {
      await loadPdfs()
      console.log('✅ loadPdfs() completed, availablePdfs now has data for header rendering')
    })()
  }, [loadPdfs])

  // Setup back button
  useEffect(() => {
    showBackButton(() => {
      hapticFeedback('light')
      navigate('/')
    })
    return () => hideBackButton()
  }, [navigate])

  // Scroll to bottom only when NOT streaming (better UX - allows user to read at their own pace)
  useEffect(() => {
    // Only auto-scroll when not actively streaming responses
    // User can scroll to read the response as it appears, no forced scrolling
    if (!isSending) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [currentConversation?.messages, isSending])

  // Helper function to style citation references in text
  const styledCitationText = (text: any) => {
    if (typeof text !== 'string') return text

    // Split text by citation pattern [1], [2], etc.
    const parts = text.split(/(\[\d+\])/g)

    return parts.map((part, idx) => {
      // Check if this part is a citation like [1], [2], etc.
      if (/^\[\d+\]$/.test(part)) {
        return (
          <span key={idx} className="text-cyan-400 font-semibold">
            {part}
          </span>
        )
      }
      return part
    })
  }

  // Helper function to process children and style citations
  const processCitations = (children: any): any => {
    if (typeof children === 'string') {
      return styledCitationText(children)
    }
    if (Array.isArray(children)) {
      return children.map((child, idx) => {
        if (typeof child === 'string') {
          return <span key={idx}>{styledCitationText(child)}</span>
        }
        return child
      })
    }
    return children
  }

  // Get selected PDF titles
  const selectedPdfTitles = availablePdfs
    .filter(pdf => selectedPdfIds.includes(pdf.id))
    .map(pdf => pdf.title)

  // Get selected documents for display component
  const selectedDocuments = (() => {
    // Now availablePdfs contains actual documents with full titles from /api/telegram/documents
    if (availablePdfs.length > 0) {
      // Filter PDFs that are in selectedPdfIds - IDs match directly now
      // e.g., selectedPdfIds has "maglib:2106", availablePdfs has id: "maglib:2106"
      const filtered = availablePdfs.filter(pdf => {
        const pdfId = String(pdf.id)
        return selectedPdfIds.includes(pdfId)
      })

      // If we found matches, use them
      if (filtered.length > 0) {
        console.log('✅ Found selected documents:', filtered.map(p => ({ id: p.id, title: p.title })))
        return filtered.map(pdf => ({
          id: pdf.id,
          title: pdf.title,
          cover: (pdf as any).cover_url, // Use the cover_url from the API response
          author: pdf.category || undefined,
          description: pdf.description,
        }))
      }
    }

    // Fallback: If availablePdfs is empty or no matches found
    console.log('📋 Using fallback for selectedPdfIds (availablePdfs not loaded):', selectedPdfIds)
    return selectedPdfIds.map((id, idx) => {
      const title = `Document ${idx + 1}`
      return {
        id,
        title,
        cover: undefined,
        author: 'Unknown',
        description: undefined,
      }
    })
  })()

  const handleSend = async () => {
    if (!input.trim() || isSending || !hasQueriesRemaining()) return

    hapticFeedback('light')
    const message = input
    setInput('')

    // Deduct query credit
    deductQuery()

    await sendMessage(message)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Wait for initialization to complete
  if (!initialized) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen px-4 bg-tg-bg">
        <p className="text-tg-hint">Loading chat...</p>
      </div>
    )
  }

  // After initialization, if still no conversation and not chatWithAll, show empty state
  if (!currentConversation && !selectedPdfIds.length && !chatWithAll) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen px-4">
        <p className="text-tg-hint text-center mb-4">Select some PDFs to start chatting</p>
        <button
          onClick={() => navigate('/archive')}
          className="bg-tg-button text-tg-button-text px-6 py-2 rounded-xl font-medium"
        >
          Browse Archive
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-tg-bg overflow-hidden">
      {/* Success toast */}
      {saveSuccess && (
        <div style={{
          position: 'fixed',
          top: '12px',
          left: '12px',
          right: '12px',
          background: 'rgba(6, 182, 212, 0.2)',
          border: '1px solid rgba(6, 182, 212, 0.5)',
          color: '#22d3ee',
          padding: '12px 16px',
          borderRadius: '8px',
          zIndex: 9999,
          fontSize: '14px',
          boxShadow: '0 2px 8px rgba(6, 182, 212, 0.3)',
        }}>
          Conversation saved successfully!
        </div>
      )}

      {/* Header - Fixed position to ensure visibility */}
      <header style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 50,
        backgroundColor: 'var(--tg-theme-bg-color, #0f1419)',
        borderBottomWidth: '1px',
        borderBottomColor: 'rgba(107, 114, 128, 0.2)',
        padding: '12px 16px',
        maxHeight: '120px',
        overflowY: 'auto'
      }} className="bg-tg-header border-b border-tg-hint/20">
        <div className="flex flex-col gap-3">
          {/* Title and buttons row */}
          <div className="flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <h1 className="text-base font-semibold text-cyan-300 text-glow truncate">
                Akasha AI
              </h1>
              <p className="text-xs text-tg-hint line-clamp-3">
                {chatWithAll
                  ? '9,078 documents'
                  : selectedPdfTitles.length > 0
                    ? selectedPdfTitles.join(' • ')
                    : `${selectedPdfIds.length} document(s) selected`
                }
              </p>
            </div>
            {/* Save and Share buttons - only show if there are messages and user is not on free tier */}
            <div className="flex-shrink-0 flex gap-2">
              {currentConversation?.messages && currentConversation.messages.length > 0 && profile?.tier !== 'free' && (
                <>
                  <button
                    onClick={async () => {
                      hapticFeedback('light')
                      // Auto-generate title from first message without showing modal
                      if (currentConversation?.messages && currentConversation.messages.length > 0) {
                        setSaveTitle(currentConversation.messages[0]?.content?.slice(0, 50) + '...' || 'Untitled Chat')
                        // Call save directly after setting title
                        setIsSavingConversation(true)
                        setSaveError(null)
                        try {
                          const title = currentConversation.messages[0]?.content?.slice(0, 50) + '...' || 'Untitled Chat'
                          const response = await fetch('/api/telegram/saved-conversations', {
                            method: 'POST',
                            headers: {
                              'Content-Type': 'application/json',
                              'X-Telegram-Init-Data': `user=${profile?.telegramId}`,
                            },
                            body: JSON.stringify({
                              conversationId: currentConversation.id,
                              title,
                              selectedDocIds: selectedPdfIds,
                            }),
                          })
                          if (!response.ok) {
                            const errorData = await response.json()
                            setSaveError(errorData.detail || 'Failed to save conversation')
                            return
                          }

                          // Parse response to get the saved conversation ID
                          const savedData = await response.json()
                          console.log('💾 Conversation saved with ID:', savedData.id)

                          // Update currentConversation with the new ID so sharing works
                          if (currentConversation) {
                            setCurrentConversation({
                              ...currentConversation,
                              id: savedData.id  // Replace 'new-' ID with actual saved ID
                            })
                          }

                          hapticFeedback('success')
                          setShowSuccess(true)
                          setTimeout(() => setShowSuccess(false), 2000)
                        } catch (err) {
                          console.error('Error saving conversation:', err)
                          setSaveError('Failed to save conversation')
                        } finally {
                          setIsSavingConversation(false)
                        }
                      }
                    }}
                    disabled={isSavingConversation}
                    className="px-3 py-1.5 bg-tg-button text-tg-button-text rounded-lg text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-60"
                  >
                    {isSavingConversation ? 'Saving...' : 'Save'}
                  </button>
                  <button
                    onClick={() => {
                      hapticFeedback('light')
                      setShowShareModal(true)
                      handleShareConversation()
                    }}
                    className="px-3 py-1.5 bg-tg-button text-tg-button-text rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
                  >
                    Share
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Selected documents display */}
          {!chatWithAll && selectedPdfIds.length > 0 && (
            <>
              {isLoadingPdfs && availablePdfs.length === 0 ? (
                // Loading state - show spinner
                <div className="mt-2 flex items-center gap-2 text-xs text-tg-hint">
                  <div className="animate-spin w-3 h-3 border border-cyan-400/30 border-t-cyan-400 rounded-full" />
                  <span>Loading documents...</span>
                </div>
              ) : (
                // Show actual documents once they're loaded
                <SelectedDocumentsDisplay
                  documents={selectedDocuments}
                  chatWithAll={chatWithAll}
                  isExpanded={isDocumentsExpanded}
                  onToggleExpand={() => setIsDocumentsExpanded(!isDocumentsExpanded)}
                />
              )}
            </>
          )}
        </div>
      </header>

      {/* Messages - accounts for fixed header */}
      <main style={{ marginTop: '120px' }} className="flex-1 overflow-y-auto px-4 py-4 chat-scrollbar">
        {currentConversation?.messages.length === 0 && (
          <div className="text-center py-8">
            <p className="text-tg-hint text-sm mb-2">Start a conversation!</p>
            <p className="text-tg-hint text-xs">Ask questions about your selected PDFs</p>
          </div>
        )}

        <div className="space-y-4">
          {currentConversation?.messages.map((message) => (
            <div
              key={message.id}
              className={clsx(
                'flex',
                message.role === 'user' ? 'justify-end' : 'justify-start'
              )}
            >
              <div
                className={clsx(
                  message.role === 'user' ? 'message-user' : 'message-assistant'
                )}
              >
                {/* Message content */}
                <div className="break-words prose prose-sm prose-invert max-w-none">
                  {message.content ? (
                    message.role === 'assistant' ? (
                      <ReactMarkdown
                        components={{
                          // Style links
                          a: ({ children, href }) => (
                            <a href={href} className="text-tg-link hover:underline" target="_blank" rel="noopener noreferrer">
                              {processCitations(children)}
                            </a>
                          ),
                          // Style paragraphs
                          p: ({ children }) => <p className="mb-2 last:mb-0">{processCitations(children)}</p>,
                          // Style lists
                          ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
                          ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>,
                          li: ({ children }) => <li className="text-tg-text">{processCitations(children)}</li>,
                          // Style headings
                          h1: ({ children }) => <h1 className="text-lg font-bold mb-2">{processCitations(children)}</h1>,
                          h2: ({ children }) => <h2 className="text-base font-bold mb-2">{processCitations(children)}</h2>,
                          h3: ({ children }) => <h3 className="text-sm font-bold mb-1">{processCitations(children)}</h3>,
                          // Style code
                          code: ({ children, className }) => {
                            const isBlock = className?.includes('language-')
                            return isBlock ? (
                              <code className="block bg-black/30 rounded p-2 text-xs overflow-x-auto">{children}</code>
                            ) : (
                              <code className="bg-black/30 rounded px-1 py-0.5 text-xs">{children}</code>
                            )
                          },
                          // Style blockquotes
                          blockquote: ({ children }) => (
                            <blockquote className="border-l-2 border-tg-hint pl-3 italic text-tg-hint">{processCitations(children)}</blockquote>
                          ),
                          // Style strong/bold
                          strong: ({ children }) => <strong className="font-semibold">{processCitations(children)}</strong>,
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    ) : (
                      <span className="whitespace-pre-wrap">{message.content}</span>
                    )
                  ) : (
                    message.isStreaming && (
                      <span className="flex space-x-1">
                        <span className="w-2 h-2 rounded-full bg-tg-hint loading-dot"></span>
                        <span className="w-2 h-2 rounded-full bg-tg-hint loading-dot"></span>
                        <span className="w-2 h-2 rounded-full bg-tg-hint loading-dot"></span>
                      </span>
                    )
                  )}
                </div>

                {/* Sources */}
                {message.sources && message.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-tg-hint/20">
                    <p className="text-xs text-tg-hint mb-2">Sources:</p>
                    <div className="space-y-1.5">
                      {message.sources.map((source, idx) => (
                        <button
                          key={idx}
                          onClick={() => {
                            hapticFeedback('light')
                            setSelectedSource(source)
                          }}
                          className="flex items-start gap-2 text-xs text-left w-full hover:bg-white/5 rounded px-1 py-0.5 -mx-1 transition-colors"
                        >
                          <span className="text-cyan-400 font-semibold flex-shrink-0">[{idx + 1}]</span>
                          <span className="text-tg-link font-medium hover:underline">{source.title}</span>
                          {source.page && (
                            <span className="text-tg-hint">(p. {source.page})</span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div ref={messagesEndRef} />
      </main>

      {/* Input */}
      <div className="sticky bottom-0 bg-tg-bg border-t border-tg-hint/20 px-4 py-3 safe-area-bottom">
        {!hasQueriesRemaining() ? (
          <div className="text-center py-2">
            <p className="text-tg-destructive text-sm mb-2">No queries remaining</p>
            <button
              onClick={() => navigate('/pricing')}
              className="text-tg-button text-sm font-medium"
            >
              Get more queries
            </button>
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question..."
              rows={1}
              className={clsx(
                'flex-1 bg-tg-secondary text-tg-text rounded-2xl px-4 py-3 resize-none',
                'placeholder:text-tg-hint focus:outline-none focus:ring-2 focus:ring-tg-button/50',
                'max-h-32'
              )}
              style={{ minHeight: '44px' }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isSending}
              className={clsx(
                'w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0',
                'transition-colors',
                input.trim() && !isSending
                  ? 'bg-tg-button text-tg-button-text'
                  : 'bg-tg-secondary text-tg-hint'
              )}
            >
              {isSending ? (
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                </svg>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Source Thumbnail Modal - rendered via portal to document.body */}
      {selectedSource && createPortal(
        <div
          onClick={() => setSelectedSource(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 99999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'rgba(0, 0, 0, 0.95)',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#1a1a24',
              border: '2px solid #06B6D4',
              borderRadius: '16px',
              padding: '20px',
              maxWidth: '90%',
              width: '320px',
              color: '#fff',
            }}
          >
            <button
              onClick={() => setSelectedSource(null)}
              style={{
                float: 'right',
                background: '#06B6D4',
                border: 'none',
                borderRadius: '50%',
                width: '30px',
                height: '30px',
                cursor: 'pointer',
                color: '#000',
                fontWeight: 'bold',
              }}
            >
              ×
            </button>
            <div style={{ marginBottom: '12px', height: '200px', background: '#252538', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {getCoverUrl(selectedSource) ? (
                <img
                  src={getCoverUrl(selectedSource)!}
                  alt=""
                  style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none'
                  }}
                />
              ) : (
                <span style={{ fontSize: '48px' }}>📚</span>
              )}
            </div>
            <h3 style={{ color: '#06B6D4', margin: '0 0 8px 0', fontSize: '16px' }}>
              {selectedSource.title}
            </h3>
            {selectedSource.channel_name && (
              <p style={{ color: '#9ca3af', margin: 0, fontSize: '14px' }}>
                by {selectedSource.channel_name}
              </p>
            )}
          </div>
        </div>,
        document.body
      )}

      {/* Save Conversation Modal */}
      <SaveConversationModal
        isOpen={showSaveModal}
        onClose={() => {
          setShowSaveModal(false)
          setSaveTitle('')
          setSaveError(null)
        }}
        onSave={handleSaveConversation}
        conversationTitle={saveTitle}
        onTitleChange={setSaveTitle}
        isSaving={isSavingConversation}
        error={saveError}
      />

      {/* Share Conversation Modal */}
      <ShareConversationModal
        isOpen={showShareModal}
        onClose={() => {
          setShowShareModal(false)
          setShareUrl(null)
          setShareError(null)
        }}
        shareUrl={shareUrl}
        isSharing={isSharing}
        error={shareError}
      />
    </div>
  )
}
