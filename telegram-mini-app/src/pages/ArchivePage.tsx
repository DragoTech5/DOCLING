import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { AlphabetBar } from '@/components/AlphabetBar'
import BottomNav from '@/components/BottomNav'
import { ENABLE_MULTI_DOCUMENT_SELECTION, SUPPORT_EMAIL_URL } from '@/config/features'

// Types
interface Document {
  id: string
  title: string
  author: string | null
  filename: string
  page_count: number
  chunk_count: number
  cover_url: string | null
  collection: 'maglib' | 'bibliothek'
  extraction_confidence?: number | null
  extraction_method?: string | null
  original_title?: string | null
}

// Cover image component - prevents broken image icons
function CoverImage({ doc, size = 'small' }: { doc: Document; size?: 'small' | 'large' }) {
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const currentUrl = doc.cover_url

  const handleError = () => {
    setLoaded(false)
    setFailed(true)
  }

  const handleLoad = () => {
    setLoaded(true)
  }

  // Placeholder component
  const Placeholder = () => (
    <div className={`w-full h-full flex items-center justify-center ${
      doc.collection === 'maglib'
        ? 'bg-gradient-to-br from-purple-900/50 to-purple-600/30'
        : 'bg-gradient-to-br from-blue-900/50 to-blue-600/30'
    }`}>
      {size === 'small' ? (
        <span className={`text-[8px] font-bold ${
          doc.collection === 'maglib' ? 'text-purple-400' : 'text-blue-400'
        }`}>
          {doc.collection === 'maglib' ? 'M' : 'B'}
        </span>
      ) : (
        <div className="text-center">
          <svg className="w-16 h-16 mx-auto text-gold-500/30" fill="currentColor" viewBox="0 0 20 20">
            <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
          </svg>
          <p className="text-gray-500 mt-2 text-sm">No cover</p>
        </div>
      )}
    </div>
  )

  // If all URLs failed, show placeholder
  if (failed || !currentUrl) {
    return <Placeholder />
  }

  // Show placeholder underneath while loading, hide image until loaded
  // This prevents broken image icon from ever showing
  return (
    <div className="relative w-full h-full">
      {/* Always show placeholder underneath as fallback */}
      <div className={`absolute inset-0 transition-opacity duration-200 ${loaded ? 'opacity-0' : 'opacity-100'}`}>
        <Placeholder />
      </div>
      {/* Image overlays placeholder when loaded */}
      <img
        src={currentUrl}
        alt=""
        className={`relative w-full h-full transition-opacity duration-200 ${
          size === 'small' ? 'object-cover' : 'object-contain bg-dark'
        } ${loaded ? 'opacity-100' : 'opacity-0'}`}
        loading="lazy"
        onError={handleError}
        onLoad={handleLoad}
      />
    </div>
  )
}

export default function ArchivePage() {
  const navigate = useNavigate()
  const { profile } = useAuthStore()
  const tier = profile?.tier ?? 'free'

  // State
  const [documents, setDocuments] = useState<Document[]>([])
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [startsWithFilter, setStartsWithFilter] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedCover, setExpandedCover] = useState<Document | null>(null)
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [chatLoading, setChatLoading] = useState(false)

  // Items per page - 30 items (10 per column × 3 columns)
  const ITEMS_PER_PAGE = 30

  // Get selection limit from tier
  const getSelectionLimit = () => {
    if (tier === 'free') return 1
    if (tier === 'starter') return 6
    if (tier === 'pro') return 15
    if (tier === 'unlimited' || tier === 'enterprise') return Infinity
    return 1
  }

  const selectionLimit = getSelectionLimit()

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const params = new URLSearchParams({
        page: page.toString(),
        per_page: ITEMS_PER_PAGE.toString(),
        collection: 'all',
      })

      if (searchQuery) {
        params.set('search', searchQuery)
      }

      if (startsWithFilter) {
        params.set('starts_with', startsWithFilter)
      }

      // Direct fetch without API client to avoid timeout issues
      // Include Telegram authentication header
      const headers: HeadersInit = {
        'Accept': 'application/json',
      }

      // Add Telegram auth header if available
      const tg = window.Telegram?.WebApp
      if (tg?.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData
      }

      const response = await fetch(`/api/telegram/documents?${params}`, {
        method: 'GET',
        headers,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: Failed to fetch documents`)
      }

      const data = await response.json()
      setDocuments(data.documents)
      setTotalPages(Math.ceil(data.total / data.per_page))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setLoading(false)
    }
  }, [page, searchQuery, startsWithFilter])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  // Toggle document selection
  const toggleSelection = (docId: string, e?: React.MouseEvent) => {
    // Don't toggle if clicking on cover expand button
    if (e && (e.target as HTMLElement).closest('.cover-expand-btn')) {
      return
    }

    setSelectedDocs(prev => {
      const newSet = new Set(prev)
      if (newSet.has(docId)) {
        newSet.delete(docId)
      } else {
        // Check limit
        if (newSet.size >= selectionLimit) {
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('warning')
          return prev
        }
        newSet.add(docId)
        window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light')
      }
      return newSet
    })
  }

  // Clear selection
  const clearSelection = () => {
    setSelectedDocs(new Set())
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('medium')
  }

  // Start chat with selected documents
  const startChat = () => {
    if (selectedDocs.size === 0) {
      // Chat with all documents - pass special flag
      navigate('/chat?docs=all')
    } else {
      // Chat with selected documents (IDs already include collection prefix: "maglib:123")
      const ids = Array.from(selectedDocs).join(',')
      navigate(`/chat?docs=${ids}`)
    }
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('medium')
  }

  // Expand cover in modal
  const openCoverModal = (doc: Document, e: React.MouseEvent) => {
    e.stopPropagation()
    setExpandedCover(doc)
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('light')
  }

  // Close cover modal
  const closeCoverModal = () => {
    setExpandedCover(null)
  }

  // Handle PDF download
  const handleDownloadPDF = async () => {
    if (!expandedCover) return

    setDownloadLoading(true)

    try {
      // Document ID is already formatted from API (e.g., "maglib:2513")
      const documentId = expandedCover.id

      // First, verify the download is valid by checking response headers only (HEAD request)
      // This checks auth and quota without downloading the file
      const headResponse = await fetch(`/api/telegram/download/${documentId}`, {
        method: 'GET',  // API doesn't support HEAD, so we check status first
        headers: {
          'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || '',
        },
      })

      // Handle non-OK responses with specific error messages
      if (!headResponse.ok) {
        let errorMessage = 'Download failed. Please try again.'
        let showUpgradeOption = false

        if (headResponse.status === 401) {
          errorMessage = 'Authentication failed. Please log in again.'
        } else if (headResponse.status === 429) {
          // Parse detailed error from backend
          try {
            const errorData = await headResponse.json()
            if (errorData.detail && typeof errorData.detail === 'string') {
              const errorDetail = JSON.parse(errorData.detail)
              if (errorDetail.code === 'download_quota_exhausted') {
                const tierName = errorDetail.tier.charAt(0).toUpperCase() + errorDetail.tier.slice(1)
                errorMessage = `⏰ Daily download limit reached!\n\nYou've used all ${tierName} plan downloads for today.\n\nUpgrade to a higher plan for more downloads.`
                showUpgradeOption = true
              }
            }
          } catch (e) {
            errorMessage = '⏰ Daily download limit reached. Upgrade your plan for more downloads.'
            showUpgradeOption = true
          }
        } else if (headResponse.status === 404) {
          errorMessage = 'PDF file not found on server. Contact support if this persists.'
        } else if (headResponse.status === 500) {
          errorMessage = 'Server error. Please try again later.'
        }

        // Try to show via Telegram popup (best UX with buttons)
        let telegramAPIFailed = false
        console.log(`[Download Error] Status: ${headResponse.status}, Message: ${errorMessage}, HasPopup: ${!!window.Telegram?.WebApp?.showPopup}`)

        if (showUpgradeOption && window.Telegram?.WebApp?.showPopup) {
          try {
            console.log('[Download] Attempting showPopup...')
            window.Telegram.WebApp.showPopup(
              {
                title: '📚 Download Limit Reached',
                message: errorMessage,
                buttons: [
                  { id: 'upgrade', type: 'default', text: '📈 View Plans' },
                  { id: 'cancel', type: 'cancel', text: 'Cancel' }
                ]
              },
              (buttonId) => {
                if (buttonId === 'upgrade') {
                  window.location.hash = '#/plans'
                }
              }
            )
            try {
              window.Telegram.WebApp.HapticFeedback?.notificationOccurred('warning')
            } catch (e) {
              // Haptic not supported, ignore
            }
          } catch (e) {
            console.warn('[Download] showPopup failed:', e)
            telegramAPIFailed = true
          }
        } else {
          console.log('[Download] showPopup not available, using fallback')
          telegramAPIFailed = true
        }

        // Fallback to Telegram alert if popup failed
        if (telegramAPIFailed && window.Telegram?.WebApp?.showAlert) {
          try {
            console.log('[Download] Attempting showAlert...')
            window.Telegram.WebApp.showAlert(errorMessage)
            try {
              window.Telegram.WebApp.HapticFeedback?.notificationOccurred('error')
            } catch (e) {
              // Haptic not supported, ignore
            }
          } catch (e) {
            console.warn('[Download] showAlert failed:', e)
            telegramAPIFailed = true
          }
        }

        // Final fallback to browser alert
        if (telegramAPIFailed) {
          console.error(`[Download] Using browser alert. Status: ${headResponse.status}, Message: ${errorMessage}`)
          alert(errorMessage)
        }

        setDownloadLoading(false)
        return
      }

      // CRITICAL FIX: Telegram WebApp sandboxes iframes and blocks blob downloads
      // Solution: Use Telegram.WebApp.openLink() which opens in browser context (bypasses sandbox)
      // This is the ONLY way to trigger actual file downloads in Telegram Mini Apps
      const downloadUrl = `/api/telegram/download/${documentId}`

      // Use openLink to trigger download in device browser (not sandboxed iframe)
      if (window.Telegram?.WebApp?.openLink) {
        // openLink() opens the URL in device browser, completely bypassing iframe sandbox
        window.Telegram.WebApp.openLink(downloadUrl)

        // Show user feedback
        try {
          window.Telegram.WebApp.showAlert(`✅ Download starting: ${expandedCover.title}.pdf`)
          window.Telegram.WebApp.HapticFeedback?.notificationOccurred('success')
        } catch (e) {
          console.log('Telegram alert unavailable')
        }

        closeCoverModal()
      } else {
        // Should never reach here in production Telegram Mini Apps
        // If we get here, Telegram API is not available - cannot download
        throw new Error('Telegram WebApp openLink is not available. Downloads only work in Telegram Mini Apps.')
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Download error'
      try {
        window.Telegram?.WebApp?.showAlert(`❌ ${errorMsg}`)
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error')
      } catch (telegramErr) {
        console.error('Download error:', errorMsg)
        alert(`Download failed: ${errorMsg}`)
      }
    } finally {
      setDownloadLoading(false)
    }
  }

  // Handle chat with this book
  const handleChatWithBook = async () => {
    if (!expandedCover) return

    setChatLoading(true)

    try {
      // Create conversation with single document
      // Note: expandedCover.id is in format "maglib:123" or "bibliothek:123"
      // Backend needs the full ID with collection prefix to determine which database to search

      const response = await fetch('/api/telegram/conversations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData || '',
        },
        body: JSON.stringify({
          pdf_ids: [expandedCover.id], // Send full ID with collection prefix (e.g., "maglib:123")
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        try {
          window.Telegram?.WebApp?.showAlert(
            errorData.detail || 'Failed to create conversation. Please try again.'
          )
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error')
        } catch (telegramErr) {
          // Telegram Web App API not available, show in console
          console.error('Failed to create conversation:', errorData.detail)
        }
        return
      }

      const conversation = await response.json()

      // Navigate to chat with the new conversation AND the specific document
      // This ensures the URL parameter is set so ChatPage properly filters to just this document
      navigate(`/chat?conversationId=${conversation.id}&docs=${expandedCover.id}`)
      try {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success')
      } catch (telegramErr) {
        // Telegram Web App API not available, ignore
      }

      closeCoverModal()
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to create conversation'
      window.Telegram?.WebApp?.showAlert(errorMsg)
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error')
    } finally {
      setChatLoading(false)
    }
  }

  // Get placeholder cover based on collection
  const getPlaceholderStyle = (collection: string) => {
    return collection === 'maglib'
      ? 'bg-gradient-to-br from-purple-900/50 to-purple-600/30 border-purple-500/30'
      : 'bg-gradient-to-br from-blue-900/50 to-blue-600/30 border-blue-500/30'
  }

  return (
    <div className="flex flex-col h-full bg-dark text-gray-100 pb-20">
      {/* Compact Header */}
      <div className="sticky top-0 z-20 bg-dark-100 border-b border-dark-300 px-3 py-2">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-lg font-bold text-cyan-400 text-glow">
            Knowledge Archive
          </h1>
        </div>

        {/* Search Bar - Compact */}
        <div className="relative mb-2">
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setPage(1)
            }}
            className="w-full bg-dark-200 border border-dark-400 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-cyan-500"
          />
          <svg
            className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
      </div>

      {/* Alphabetical Quickswitch Navigation */}
      <AlphabetBar
        activeLetter={startsWithFilter}
        onLetterClick={(letter) => {
          setStartsWithFilter(letter)
          setPage(1)
        }}
      />

      {/* Selection Summary Bar - Hidden when multi-doc selection is disabled */}
      {ENABLE_MULTI_DOCUMENT_SELECTION && selectedDocs.size > 0 && (
        <div className="bg-cyan-500/10 border-b border-cyan-500/30 px-3 py-2 flex items-center justify-between">
          <span className="text-sm text-cyan-400">
            Selected: {selectedDocs.size}/{selectionLimit === Infinity ? '∞' : selectionLimit}
          </span>
          <button
            onClick={clearSelection}
            className="text-xs text-gray-400 hover:text-cyan-400 px-2 py-1"
          >
            Clear
          </button>
        </div>
      )}

      {/* Document List - 3 Column Compact View */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="w-6 h-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center text-red-400 p-4">
            <p className="text-sm">{error}</p>
            <button
              onClick={fetchDocuments}
              className="mt-2 text-cyan-400 hover:text-cyan-300 text-sm"
            >
              Retry
            </button>
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center text-gray-400 p-8">
            <p className="text-sm">No documents found</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-px bg-dark-300">
            {documents.map((doc) => (
              <div
                key={doc.id}
                onClick={(e) => ENABLE_MULTI_DOCUMENT_SELECTION && toggleSelection(doc.id, e)}
                className={`flex items-start gap-2 p-2 ${ENABLE_MULTI_DOCUMENT_SELECTION ? 'cursor-pointer' : 'cursor-default'} transition-colors ${
                  selectedDocs.has(doc.id)
                    ? 'bg-cyan-500/20'
                    : 'bg-dark-100 hover:bg-dark-200'
                }`}
              >
                {/* Thumbnail - Small & Clickable */}
                <button
                  className={`cover-expand-btn flex-shrink-0 w-8 h-12 rounded overflow-hidden border ${getPlaceholderStyle(doc.collection)} hover:ring-1 hover:ring-cyan-500/50`}
                  onClick={(e) => openCoverModal(doc, e)}
                  title="Click to enlarge"
                >
                  <CoverImage doc={doc} size="small" />
                </button>

                {/* Title & Author */}
                <div className="flex-1 min-w-0 py-0.5">
                  <h3 className={`text-[11px] leading-tight line-clamp-2 ${
                    selectedDocs.has(doc.id) ? 'text-cyan-300' : 'text-gray-200'
                  }`}>
                    {doc.title}
                  </h3>
                  {doc.author && (
                    <p className="text-[9px] text-gray-500 mt-0.5 truncate">
                      {doc.author}
                    </p>
                  )}
                </div>

                {/* Selection Indicator - Only show if multi-doc selection is enabled */}
                {ENABLE_MULTI_DOCUMENT_SELECTION && selectedDocs.has(doc.id) && (
                  <div className="flex-shrink-0 w-4 h-4 rounded-full bg-cyan-500 flex items-center justify-center mt-0.5">
                    <svg className="w-2.5 h-2.5 text-dark" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination - Improved Visibility */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 py-3 border-t border-dark-300 bg-dark-100/95 backdrop-blur-sm">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-2 rounded-lg bg-dark-200 text-gray-200 text-sm font-medium disabled:opacity-30 disabled:text-gray-500 hover:bg-dark-300 transition-colors"
          >
            ←
          </button>
          <span className="text-sm font-semibold text-gray-200 min-w-[60px] text-center">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-2 rounded-lg bg-dark-200 text-gray-200 text-sm font-medium disabled:opacity-30 disabled:text-gray-500 hover:bg-dark-300 transition-colors"
          >
            →
          </button>
        </div>
      )}

      {/* Bottom Action Bar */}
      <div className="sticky bottom-16 z-30 bg-dark-100 border-t border-dark-300 p-3">
        <button
          onClick={startChat}
          className="w-full py-2.5 rounded-xl bg-cyan-500 text-dark font-semibold text-sm btn-glow hover:bg-cyan-400 transition-colors"
        >
          Chat
        </button>
      </div>

      {/* Cover Modal */}
      {expandedCover && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={closeCoverModal}
        >
          <div
            className="relative max-w-sm w-full bg-dark-100 rounded-xl overflow-y-auto shadow-2xl max-h-[calc(100vh-120px)] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              onClick={closeCoverModal}
              className="absolute top-2 right-2 z-10 w-8 h-8 rounded-full bg-dark/80 text-white flex items-center justify-center hover:bg-dark"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            {/* Document Info - with bottom padding to account for nav bar */}
            <div className="p-4 pb-24">
              <h3 className="text-lg font-semibold text-gray-100 mb-1">
                {expandedCover.title}
              </h3>
              {expandedCover.author && (
                <p className="text-sm text-gray-400 mb-3">
                  by {expandedCover.author}
                </p>
              )}

              {/* Extraction Metadata */}
              {expandedCover.extraction_method && (
                <div className="mb-3 p-3 bg-dark-200/50 rounded-lg border border-cyan-500/20">
                  <p className="text-xs text-gray-400 mb-2">Title Extraction Info:</p>
                  {expandedCover.original_title && expandedCover.original_title !== expandedCover.title && (
                    <div className="text-xs mb-2">
                      <span className="text-gray-500">Original: </span>
                      <span className="text-gray-300 italic">"{expandedCover.original_title}"</span>
                    </div>
                  )}
                  <div className="flex gap-3 text-xs">
                    {expandedCover.extraction_method && (
                      <span className={`px-2 py-1 rounded ${
                        expandedCover.extraction_method === 'llm'
                          ? 'bg-blue-500/20 text-blue-400'
                          : 'bg-green-500/20 text-green-400'
                      }`}>
                        {expandedCover.extraction_method === 'llm' ? 'AI Extracted' : 'Auto Extracted'}
                      </span>
                    )}
                    {expandedCover.extraction_confidence !== null && expandedCover.extraction_confidence !== undefined && (
                      <span className={`px-2 py-1 rounded ${
                        expandedCover.extraction_confidence >= 0.9
                          ? 'bg-green-500/20 text-green-400'
                          : expandedCover.extraction_confidence >= 0.8
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-red-500/20 text-red-400'
                      }`}>
                        {(expandedCover.extraction_confidence * 100).toFixed(0)}% confident
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Pages count only */}
              <div className="text-xs text-gray-500 mb-4">
                <span>{expandedCover.page_count} pages</span>
              </div>

              {/* Thumbnail and Action buttons in horizontal layout */}
              <div className="flex items-center justify-center gap-6 mb-4">
                {/* Cover Image - increased by 36% */}
                <div className={`aspect-[2/3] max-w-96 ${getPlaceholderStyle(expandedCover.collection)}`}>
                  <CoverImage doc={expandedCover} size="large" />
                </div>

                {/* Action buttons vertical stack */}
                <div className="flex flex-col gap-2 flex-shrink-0">
                {/* Download PDF Button */}
                <button
                  onClick={handleDownloadPDF}
                  disabled={downloadLoading || chatLoading}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    downloadLoading || chatLoading
                      ? 'bg-gray-500/20 text-gray-400 cursor-not-allowed'
                      : 'bg-green-500/20 text-green-400 hover:bg-green-500/30 active:bg-green-500/40'
                  }`}
                >
                  {downloadLoading ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" fill="none" opacity="0.3" />
                        <path strokeLinecap="round" d="M12 2a10 10 0 0 1 0 20" strokeWidth="2" />
                      </svg>
                      Downloading...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Download PDF
                    </>
                  )}
                </button>

                {/* Chat with This Book Button */}
                <button
                  onClick={handleChatWithBook}
                  disabled={downloadLoading || chatLoading}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    downloadLoading || chatLoading
                      ? 'bg-gray-500/20 text-gray-400 cursor-not-allowed'
                      : 'bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 active:bg-cyan-500/40'
                  }`}
                >
                  {chatLoading ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" fill="none" opacity="0.3" />
                        <path strokeLinecap="round" d="M12 2a10 10 0 0 1 0 20" strokeWidth="2" />
                      </svg>
                      Starting...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                      Chat with This Book
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Support Contact Section */}
            <div className="mt-4 pt-4 border-t border-gray-800/30">
              <div className="flex items-start gap-2">
                <svg className="w-4 h-4 text-gray-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <p className="text-xs text-gray-500">
                  Need help?{' '}
                  <a href={SUPPORT_EMAIL_URL} className="text-gray-400 hover:text-gray-300 underline transition-colors">
                    Contact support
                  </a>
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
      )}

      <BottomNav />
    </div>
  )
}
