import { useRef, useEffect, useState } from 'react'

interface AlphabetBarProps {
  activeLetter: string | null
  onLetterClick: (letter: string) => void
}

export function AlphabetBar({ activeLetter, onLetterClick }: AlphabetBarProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [isScrollable, setIsScrollable] = useState(false)

  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

  useEffect(() => {
    const container = scrollContainerRef.current
    if (container) {
      // Check if scrollable (content wider than container)
      setIsScrollable(container.scrollWidth > container.clientWidth)
    }
  }, [])

  // Scroll active letter into view smoothly
  useEffect(() => {
    if (activeLetter && scrollContainerRef.current) {
      const container = scrollContainerRef.current
      const activeBtn = container.querySelector(`[data-letter="${activeLetter}"]`) as HTMLElement
      if (activeBtn) {
        // Scroll smoothly to center the active letter
        const containerCenter = container.clientWidth / 2
        const buttonCenter = activeBtn.offsetLeft + activeBtn.clientWidth / 2
        const scrollNeeded = buttonCenter - containerCenter

        container.scrollBy({
          left: scrollNeeded,
          behavior: 'smooth',
        })
      }
    }
  }, [activeLetter])

  return (
    <div className="bg-dark-100 border-b border-dark-300 px-2 py-2.5">
      {/* Alphabet scroll bar */}
      <div
        ref={scrollContainerRef}
        className="flex gap-1 overflow-x-auto scrollbar-hide snap-x snap-mandatory"
        style={{
          scrollBehavior: 'smooth',
          WebkitOverflowScrolling: 'touch',
        }}
      >
        {letters.map((letter) => (
          <button
            key={letter}
            data-letter={letter}
            onClick={() => onLetterClick(letter)}
            className={`
              flex-shrink-0 w-7 h-7 rounded text-xs font-semibold snap-center
              transition-all duration-200 ease-out
              ${
                activeLetter === letter
                  ? 'bg-gold-500 text-dark shadow-lg shadow-gold-500/40 ring-1 ring-gold-400'
                  : 'bg-dark-300 text-gray-400 hover:bg-dark-400 hover:text-gold-300'
              }
            `}
            title={`Jump to ${letter}`}
          >
            {letter}
          </button>
        ))}
      </div>

      {/* Scrollbar indicator (hidden by default) */}
      {isScrollable && (
        <div className="mt-1 h-0.5 bg-gradient-to-r from-transparent via-gold-500/30 to-transparent" />
      )}
    </div>
  )
}
