import { useState } from 'react'
import { clsx } from 'clsx'

interface SelectedDocument {
  id: string
  title: string
  cover?: string
  author?: string
  description?: string
}

interface SelectedDocumentsDisplayProps {
  documents: SelectedDocument[]
  chatWithAll?: boolean
  isExpanded?: boolean
  onToggleExpand?: () => void
  chatCompact?: boolean // Compact horizontal layout for chat page
}

export function SelectedDocumentsDisplay({
  documents,
  chatWithAll = false,
  isExpanded = false,
  onToggleExpand,
  chatCompact = false,
}: SelectedDocumentsDisplayProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)

  // Don't show if no documents
  if (documents.length === 0 && !chatWithAll) {
    return null
  }

  // Chat compact mode - single horizontal row with thumbnails and minimal info
  if (chatCompact) {
    return (
      <div className="flex items-center gap-3 py-2 overflow-x-auto pb-2">
        {documents.map((doc, idx) => (
          <div key={doc.id} className="flex flex-col items-center gap-1 flex-shrink-0">
            {/* Compact thumbnail */}
            <div className="relative w-12 h-16 rounded-sm overflow-hidden border border-tg-button/40 shadow-md">
              {/* Fallback gradient background */}
              <div className="absolute inset-0 bg-gradient-to-br from-tg-button/10 to-tg-button/5 flex items-center justify-center">
                <span className="text-[10px] font-serif font-bold text-tg-button">
                  {idx + 1}
                </span>
              </div>
              {/* Cover image */}
              {doc.cover && (
                <img
                  src={doc.cover}
                  alt={doc.title}
                  className="w-full h-full object-cover relative z-10"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none'
                  }}
                />
              )}
              {/* Index badge */}
              <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-tg-button text-dark text-[10px] font-serif font-bold flex items-center justify-center shadow-lg">
                {idx + 1}
              </div>
            </div>
            {/* Compact title */}
            <p className="text-[10px] font-serif text-tg-text text-center line-clamp-1 w-14">
              {doc.title.substring(0, 20)}
            </p>
          </div>
        ))}
      </div>
    )
  }

  // Compact view - show count and toggle button
  if (!isExpanded) {
    return (
      <div className="mt-2 space-y-2">
        <button
          onClick={onToggleExpand}
          className="group flex items-center gap-2 text-xs font-serif tracking-wide text-tg-hint hover:text-tg-text transition-colors duration-300"
        >
          <span className="font-serif italic opacity-75">Selected</span>
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-tg-hint/10 group-hover:bg-gold-400/20 transition-colors duration-300">
            <span className="text-xs font-semibold text-gold-400">
              {chatWithAll ? '∞' : documents.length}
            </span>
          </span>
          <svg
            className="w-3 h-3 opacity-50 group-hover:opacity-100 transition-opacity duration-300"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </button>

        {/* Horizontal thumbnail preview - show all documents */}
        {documents.length > 0 && (
          <div className="flex gap-3 flex-wrap">
            {documents.map((doc, idx) => (
              <div key={doc.id} className="flex flex-col gap-1">
                <div className="relative w-14 h-20 rounded-sm overflow-hidden border border-gold-400/30 hover:border-gold-400/70 transition-all duration-300 shadow-md hover:shadow-lg hover:shadow-gold-400/20">
                  {/* Fallback gradient background - always visible, hidden when image loads */}
                  <div className="absolute inset-0 bg-gradient-to-br from-gold-400/10 to-gold-400/5 flex flex-col items-center justify-center">
                    <span className="text-xs font-serif font-bold text-gold-400">
                      {idx + 1}
                    </span>
                    <span className="text-xs font-serif text-tg-hint/60 text-center px-1 line-clamp-2 leading-tight text-wrap break-words">
                      {doc.title.substring(0, 15)}
                    </span>
                  </div>
                  {/* Cover image - overlays the fallback when loaded */}
                  {doc.cover && (
                    <img
                      src={doc.cover}
                      alt={doc.title}
                      className="w-full h-full object-cover relative z-10"
                      onError={(e) => {
                        // Hide broken image to show fallback underneath
                        e.currentTarget.style.display = 'none'
                      }}
                    />
                  )}
                  {/* Index badge */}
                  <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-gold-400 text-dark text-xs font-serif font-bold flex items-center justify-center shadow-lg">
                    {idx + 1}
                  </div>
                </div>
                {/* Title below thumbnail */}
                <p className="text-xs font-serif text-tg-text line-clamp-2 w-16 leading-tight">
                  {doc.title}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Expanded view - full document list with editorial styling
  return (
    <div className="mt-3 space-y-3 border-t border-tg-hint/10 pt-3">
      <button
        onClick={onToggleExpand}
        className="group flex items-center gap-2 text-xs font-serif tracking-wide text-gold-400 hover:text-gold-300 transition-colors duration-300"
      >
        <span className="font-serif italic">Selected Documents</span>
        <svg
          className="w-3 h-3 group-hover:translate-y-0.5 transition-transform duration-300"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 10l7 7 7-7"
          />
        </svg>
      </button>

      {chatWithAll ? (
        <div className="px-3 py-2 bg-tg-hint/5 rounded-lg border border-gold-400/20">
          <p className="text-xs text-tg-text font-medium">All Collections</p>
          <p className="text-xs text-tg-hint mt-1">
            9,078 documents
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {documents.map((doc, idx) => (
            <div
              key={doc.id}
              className={clsx(
                'group flex gap-3 p-2 rounded-lg transition-all duration-300 cursor-pointer',
                hoveredIndex === idx
                  ? 'bg-gold-400/10 border border-gold-400/40'
                  : 'bg-tg-hint/5 border border-tg-hint/10 hover:border-gold-400/20'
              )}
              onMouseEnter={() => setHoveredIndex(idx)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              {/* Thumbnail */}
              <div className="relative flex-shrink-0 w-14 h-20 rounded-sm overflow-hidden border border-gold-400/20 shadow-md">
                {/* Fallback gradient background - always visible, hidden when image loads */}
                <div className="absolute inset-0 w-full h-full bg-gradient-to-br from-tg-hint/30 to-tg-hint/10 flex items-center justify-center">
                  <span className="text-xs font-serif text-tg-hint/60 text-center px-1 line-clamp-3">
                    {doc.title}
                  </span>
                </div>
                {/* Cover image - overlays the fallback when loaded */}
                {doc.cover && (
                  <img
                    src={doc.cover}
                    alt={doc.title}
                    className="w-full h-full object-cover relative z-10"
                    onError={(e) => {
                      // Hide broken image to show fallback underneath
                      e.currentTarget.style.display = 'none'
                    }}
                  />
                )}
                {/* Index badge */}
                <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-gold-400 text-dark text-xs font-serif font-bold flex items-center justify-center shadow-lg">
                  {idx + 1}
                </div>
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-serif text-tg-text line-clamp-2 group-hover:text-gold-400 transition-colors duration-300">
                  {doc.title}
                </h4>
                {doc.author && (
                  <p className="text-xs text-tg-hint mt-1 truncate">
                    {doc.author}
                  </p>
                )}
                <p className="text-xs text-tg-hint/60 mt-1.5 font-mono tracking-tighter">
                  {doc.id}
                </p>
              </div>

              {/* Accent line on hover */}
              <div
                className="absolute bottom-0 left-0 h-0.5 bg-gradient-to-r from-gold-400 to-transparent group-hover:w-full transition-all duration-500"
                style={{
                  width: hoveredIndex === idx ? '100%' : '0%',
                }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
