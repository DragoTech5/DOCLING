import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { hapticFeedback } from '@/lib/telegram'
import { clsx } from 'clsx'
import type { Source } from '@/types'

// Helper function to style citation text (references like [1], [2], etc.)
const styledCitationText = (text: string): (string | React.ReactElement)[] => {
  const citationRegex = /\[(\d+)\]/g
  const parts = text.split(citationRegex)
  return parts.map((part, idx) => {
    // Even indices are text, odd indices are citation numbers
    if (idx % 2 === 1) {
      return (
        <span key={idx} className="text-cyan-400 font-semibold">
          {`[${part}]`}
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

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  timestamp?: string
  isStreaming?: boolean
}

interface SharedConversation {
  id: string
  title: string
  messages: Message[]
  documents: Array<{ id: string }>
  createdAt: string
  updatedAt: string
}

// Helper to get cover URL for a source
function getCoverUrl(source: Source): string | null {
  if (source.document_filename) {
    return `/covers/maglib/${encodeURIComponent(source.document_filename)}.jpg`
  }
  return null
}

export default function SharePage() {
  const { shareToken } = useParams()
  const navigate = useNavigate()
  const [conversation, setConversation] = useState<SharedConversation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedSource, setSelectedSource] = useState<Source | null>(null)

  // Fetch shared conversation
  useEffect(() => {
    const fetchSharedConversation = async () => {
      if (!shareToken) {
        setError('Invalid share link')
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        setError(null)

        const response = await fetch(`/api/telegram/share/${shareToken}`)

        if (!response.ok) {
          if (response.status === 404) {
            setError('Shared conversation not found or has expired')
          } else {
            setError('Failed to load shared conversation')
          }
          setLoading(false)
          return
        }

        const data = await response.json()
        setConversation(data)
      } catch (err) {
        console.error('Error fetching shared conversation:', err)
        setError('Failed to load shared conversation')
      } finally {
        setLoading(false)
      }
    }

    fetchSharedConversation()
  }, [shareToken])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen px-4 bg-tg-bg">
        <p className="text-tg-hint">Loading shared conversation...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen px-4 bg-tg-bg">
        <p className="text-tg-destructive text-center mb-4">{error}</p>
        <button
          onClick={() => navigate('/')}
          className="bg-tg-button text-tg-button-text px-6 py-2 rounded-xl font-medium"
        >
          Go Home
        </button>
      </div>
    )
  }

  if (!conversation) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen px-4 bg-tg-bg">
        <p className="text-tg-hint text-center mb-4">Conversation not found</p>
        <button
          onClick={() => navigate('/')}
          className="bg-tg-button text-tg-button-text px-6 py-2 rounded-xl font-medium"
        >
          Go Home
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-tg-bg">
      {/* Promotional Banner - Curiosity-Driven */}
      <div
        onClick={() => {
          hapticFeedback('light')
          // @ts-ignore - openLink is valid Telegram API method
          window.Telegram?.WebApp?.openLink('https://web.telegram.org/k/#@AkashaAIHub_bot')
        }}
        style={{
          background: 'linear-gradient(135deg, rgba(0, 12, 25, 0.98) 0%, rgba(8, 28, 48, 0.98) 50%, rgba(0, 20, 40, 0.98) 100%)',
          borderBottom: '3px solid rgba(6, 182, 212, 0.5)',
          padding: '16px 14px',
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '10px',
          zIndex: 50,
          position: 'relative',
          overflow: 'hidden',
        }}
        className="hover:scale-100 transition-all group"
      >
        {/* Animated glow effect */}
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'radial-gradient(ellipse 600px 120px at center, rgba(6, 182, 212, 0.08) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />

        {/* Main Headline - Curiosity Gap */}
        <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', width: '100%' }}>
          <p style={{
            color: '#EF4444',
            margin: '0 0 4px 0',
            fontSize: '10px',
            fontWeight: '800',
            letterSpacing: '1.5px',
            textTransform: 'uppercase',
            opacity: 0.9,
          }}>
            ⚡ THEY DON'T WANT YOU HERE
          </p>
          <p style={{
            color: '#06B6D4',
            margin: 0,
            fontSize: '15px',
            fontWeight: '900',
            lineHeight: '1.2',
            letterSpacing: '0.3px',
          }}>
            AKASHA AI — The Hidden Knowledge
          </p>
          <p style={{
            color: '#A78BFA',
            margin: '2px 0 0 0',
            fontSize: '11px',
            fontWeight: '700',
            letterSpacing: '0.8px',
          }}>
            ◆ UNCENSORED • UNFILTERED • FORBIDDEN ◆
          </p>
        </div>

        {/* Curiosity Copy - Call to action */}
        <p style={{
          color: '#FCD34D',
          margin: '4px 0 0 0',
          fontSize: '9.5px',
          fontWeight: '600',
          lineHeight: '1.35',
          textAlign: 'center',
          maxWidth: '100%',
        }}>
          9,000+ Occult Wisdom, Conspiracies & Hidden Truths<br/>
          <span style={{ color: '#D0D8E0', fontSize: '8.5px' }}>No gatekeepers. No algorithms burying truth. Chat with forbidden knowledge.</span>
        </p>

        {/* CTA with urgency */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '6px',
          marginTop: '6px',
          position: 'relative',
          zIndex: 1,
        }}>
          <span style={{
            color: '#06B6D4',
            fontSize: '13px',
            fontWeight: 'bold',
            opacity: 1,
            animation: 'pulse 2s infinite',
          }}>
            ✨
          </span>
          <p style={{
            color: '#E0E7FF',
            margin: 0,
            fontSize: '10px',
            fontWeight: '700',
            letterSpacing: '0.3px',
          }}>
            Join Thousands Awakened
          </p>
          <span style={{
            color: '#06B6D4',
            fontSize: '13px',
            fontWeight: 'bold',
            opacity: 1,
            animation: 'pulse 2s infinite',
          }}>
            ✨
          </span>
        </div>

        {/* Pulse animation */}
        <style>{`
          @keyframes pulse {
            0%, 100% { opacity: 0.6; }
            50% { opacity: 1; }
          }
        `}</style>
      </div>

      {/* Header */}
      <header className="sticky top-0 z-10 bg-tg-header border-b border-tg-hint/20 px-4 py-3">
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              hapticFeedback('light')
              navigate('/')
            }}
            className="text-tg-button text-xl leading-none"
          >
            ←
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-semibold text-tg-text truncate">
              {conversation.title}
            </h1>
            <p className="text-xs text-tg-hint truncate">Shared Conversation</p>
          </div>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-4 py-4 chat-scrollbar">
        {conversation.messages.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-tg-hint text-sm">No messages in this conversation</p>
          </div>
        ) : (
          <div className="space-y-4">
            {conversation.messages.map((message) => (
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
                            a: ({ children, href }) => (
                              <a href={href} className="text-tg-link hover:underline" target="_blank" rel="noopener noreferrer">
                                {children}
                              </a>
                            ),
                            p: ({ children }) => <p className="mb-2 last:mb-0">{processCitations(children)}</p>,
                            ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>,
                            li: ({ children }) => <li className="text-tg-text">{processCitations(children)}</li>,
                            h1: ({ children }) => <h1 className="text-lg font-bold mb-2">{processCitations(children)}</h1>,
                            h2: ({ children }) => <h2 className="text-base font-bold mb-2">{processCitations(children)}</h2>,
                            h3: ({ children }) => <h3 className="text-sm font-bold mb-1">{processCitations(children)}</h3>,
                            code: ({ children, className }) => {
                              const isBlock = className?.includes('language-')
                              return isBlock ? (
                                <code className="block bg-black/30 rounded p-2 text-xs overflow-x-auto">{children}</code>
                              ) : (
                                <code className="bg-black/30 rounded px-1 py-0.5 text-xs">{children}</code>
                              )
                            },
                            blockquote: ({ children }) => (
                              <blockquote className="border-l-2 border-tg-hint pl-3 italic text-tg-hint">{processCitations(children)}</blockquote>
                            ),
                            strong: ({ children }) => <strong className="font-semibold">{processCitations(children)}</strong>,
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      ) : (
                        <span className="whitespace-pre-wrap">{message.content}</span>
                      )
                    ) : null}
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
                            <span className="text-gold-400 font-semibold flex-shrink-0">[{idx + 1}]</span>
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
        )}
      </main>

      {/* Source Thumbnail Modal */}
      {selectedSource && (
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
              border: '2px solid #D4AF37',
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
                background: '#D4AF37',
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
            <h3 style={{ color: '#D4AF37', margin: '0 0 8px 0', fontSize: '16px' }}>
              {selectedSource.title}
            </h3>
            {selectedSource.channel_name && (
              <p style={{ color: '#9ca3af', margin: 0, fontSize: '14px' }}>
                by {selectedSource.channel_name}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
