import { useState } from 'react'

export default function MysticalTeaserCard() {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="px-4 py-4">
      {/* Mystical container with glow effect */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Cinzel:wght@400;600;700&display=swap');

        .mystical-card {
          background: linear-gradient(135deg, rgba(15, 23, 42, 0.8) 0%, rgba(30, 20, 50, 0.6) 100%);
          border: 2px solid rgba(34, 211, 238, 0.3);
          position: relative;
          overflow: hidden;
          transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .mystical-card::before {
          content: '';
          position: absolute;
          top: -50%;
          right: -50%;
          width: 200%;
          height: 200%;
          background: radial-gradient(circle, rgba(34, 211, 238, 0.15) 0%, transparent 70%);
          animation: mysticalGlow 8s ease-in-out infinite;
          pointer-events: none;
        }

        .mystical-card::after {
          content: '';
          position: absolute;
          inset: 0;
          background:
            linear-gradient(45deg, transparent 30%, rgba(168, 85, 247, 0.05) 50%, transparent 70%),
            linear-gradient(-45deg, transparent 30%, rgba(34, 211, 238, 0.03) 50%, transparent 70%);
          pointer-events: none;
        }

        @keyframes mysticalGlow {
          0%, 100% {
            transform: translate(0, 0) scale(1);
            opacity: 0.5;
          }
          50% {
            transform: translate(10px, -10px) scale(1.1);
            opacity: 0.8;
          }
        }

        .mystical-card:hover {
          border-color: rgba(34, 211, 238, 0.6);
          box-shadow: 0 0 30px rgba(34, 211, 238, 0.2), inset 0 0 20px rgba(34, 211, 238, 0.05);
          transform: translateY(-2px);
        }

        .teaser-title {
          font-family: 'Cinzel', serif;
          font-size: 1.5rem;
          font-weight: 700;
          letter-spacing: 0.05em;
          background: linear-gradient(120deg, #22d3ee 0%, #a855f7 50%, #22d3ee 100%);
          background-size: 200% auto;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
          animation: shimmer 4s linear infinite;
        }

        @keyframes shimmer {
          0% { background-position: 0% center; }
          100% { background-position: 200% center; }
        }

        .teaser-subtitle {
          font-family: 'Orbitron', sans-serif;
          font-size: 0.75rem;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          color: rgba(168, 85, 247, 0.7);
          margin-top: 0.5rem;
        }

        .expand-icon {
          transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .expand-icon.expanded {
          transform: rotate(180deg);
        }

        .expanded-content {
          font-family: 'Cinzel', serif;
          font-size: 0.95rem;
          line-height: 1.7;
          color: rgba(226, 232, 240, 0.85);
          letter-spacing: 0.01em;
        }

        .content-reveal {
          animation: slideDown 0.5s cubic-bezier(0.4, 0, 0.2, 1);
        }

        @keyframes slideDown {
          from {
            opacity: 0;
            max-height: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            max-height: 500px;
            transform: translateY(0);
          }
        }

        .mystical-divider {
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(34, 211, 238, 0.3), transparent);
          margin: 1rem 0;
        }

        .knowledge-highlight {
          color: #06b6d4;
          font-weight: 600;
          text-shadow: 0 0 10px rgba(34, 211, 238, 0.3);
        }

        .occult-symbol {
          display: inline-block;
          font-size: 0.8em;
          opacity: 0.6;
          margin: 0 0.25rem;
        }
      `}</style>

      {/* Main Card */}
      <div
        className="mystical-card rounded-2xl p-6 cursor-pointer relative z-10"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {/* Content wrapper */}
        <div className="relative z-20">
          {/* Teaser Section - Always Visible */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <h2 className="teaser-title">
                The Knowledge They Try to Hide
              </h2>
              <p className="teaser-subtitle">
                <span className="occult-symbol">◆</span>
                Uncensored • Unfiltered • Forbidden
                <span className="occult-symbol">◆</span>
              </p>
              <p className="text-gray-400 text-sm mt-3 leading-relaxed">
                9,000+ books on <span className="knowledge-highlight">occult wisdom</span>, <span className="knowledge-highlight">esoteric secrets</span>, and <span className="knowledge-highlight">hidden truths</span>
              </p>
            </div>
            <svg
              className={`expand-icon ${isExpanded ? 'expanded' : ''} w-6 h-6 text-cyan-400 flex-shrink-0 mt-1`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </div>

          {/* Expanded Content */}
          {isExpanded && (
            <div className="content-reveal">
              <div className="mystical-divider" />
              <div className="expanded-content space-y-3">
                <p>
                  No censorship. No algorithms burying the truth. No gatekeepers controlling what you learn.
                </p>
                <p>
                  Chat with <span className="knowledge-highlight">conspiracy archives</span>, <span className="knowledge-highlight">occult libraries</span>, and <span className="knowledge-highlight">forbidden philosophy</span>—everything suppressed by mainstream platforms.
                </p>
                <p className="text-cyan-300/80 font-semibold">
                  Raw knowledge. Unfiltered access. Limited seats remaining.
                </p>
                <p className="text-purple-300/70 text-sm pt-2">
                  Join thousands already awakened to what they don't want you to know.
                </p>
              </div>
            </div>
          )}

          {/* CTA Section */}
          {isExpanded && (
            <div className="mt-4 pt-3 border-t border-cyan-500/20">
              <p className="text-xs text-gray-500 mb-3">
                Tap anywhere to collapse
              </p>
            </div>
          )}

          {/* Always visible hint */}
          {!isExpanded && (
            <p className="text-xs text-cyan-400/60 mt-3 animate-pulse">
              Tap to reveal the full archive...
            </p>
          )}
        </div>
      </div>

      {/* Mystical accent lines below card */}
      <div className="flex justify-center gap-2 mt-3 opacity-30">
        <div className="w-1 h-1 rounded-full bg-cyan-400" />
        <div className="w-1 h-1 rounded-full bg-purple-400" />
        <div className="w-1 h-1 rounded-full bg-cyan-400" />
      </div>
    </div>
  )
}
