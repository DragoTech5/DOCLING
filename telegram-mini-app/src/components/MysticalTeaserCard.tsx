import { useState, useMemo } from 'react'

export default function MysticalTeaserCard() {
  const [isExpanded, setIsExpanded] = useState(false)

  // Auto-detect user language
  const userLanguage = useMemo(() => {
    return window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code || 'en'
  }, [])

  // Multilingual translations
  const translations: Record<string, Record<string, string>> = {
    en: {
      title: 'The Knowledge They Try to Hide',
      subtitle: 'Uncensored • Unfiltered • Forbidden',
      description: '9,000+ books on occult wisdom, esoteric secrets, conspiracies, and hidden truths',
      occultWisdom: 'occult wisdom',
      esotericSecrets: 'esoteric secrets',
      conspiracies: 'conspiracies',
      hiddenTruths: 'hidden truths',
      noCensorship: 'No censorship. No algorithms burying the truth. No gatekeepers controlling what you learn.',
      chatWith: 'Chat with conspiracy archives, occult libraries, and forbidden philosophy—everything suppressed by mainstream platforms.',
      conspircyArchives: 'conspiracy archives',
      occultLibraries: 'occult libraries',
      forbiddenPhilosophy: 'forbidden philosophy',
      rawKnowledge: 'Raw knowledge. Unfiltered access. Limited seats remaining.',
      joinThousands: 'Join thousands already awakened to what they don\'t want you to know.',
      tapReveal: 'Tap to reveal the full archive...',
      tapCollapse: 'Tap anywhere to collapse'
    },
    es: {
      title: 'El Conocimiento Que Intentan Occultar',
      subtitle: 'Sin Censura • Sin Filtros • Prohibido',
      description: '9,000+ libros sobre sabiduría oculta, secretos esotéricos, conspiraciones y verdades ocultas',
      occultWisdom: 'sabiduría oculta',
      esotericSecrets: 'secretos esotéricos',
      conspiracies: 'conspiraciones',
      hiddenTruths: 'verdades ocultas',
      noCensorship: 'Sin censura. Sin algoritmos ocultando la verdad. Sin guardianes controlando lo que aprendes.',
      chatWith: 'Chatea con archivos de conspiración, bibliotecas ocultas y filosofía prohibida—todo suprimido por plataformas convencionales.',
      conspircyArchives: 'archivos de conspiración',
      occultLibraries: 'bibliotecas ocultas',
      forbiddenPhilosophy: 'filosofía prohibida',
      rawKnowledge: 'Conocimiento puro. Acceso sin filtros. Plazas limitadas disponibles.',
      joinThousands: 'Únete a miles ya despertados a lo que no quieren que sepas.',
      tapReveal: 'Toca para revelar el archivo completo...',
      tapCollapse: 'Toca en cualquier lugar para cerrar'
    },
    fr: {
      title: 'Le Savoir Qu\'ils Essaient de Cacher',
      subtitle: 'Non Censuré • Non Filtré • Interdit',
      description: '9,000+ livres sur la sagesse occulte, les secrets ésotériques, les conspirations et les vérités cachées',
      occultWisdom: 'sagesse occulte',
      esotericSecrets: 'secrets ésotériques',
      conspiracies: 'conspirations',
      hiddenTruths: 'vérités cachées',
      noCensorship: 'Aucune censure. Aucun algorithme cachant la vérité. Aucun gardien contrôlant ce que tu apprends.',
      chatWith: 'Discute avec des archives de conspiration, des bibliothèques occultes et de la philosophie interdite—tout supprimé par les plateformes dominantes.',
      conspircyArchives: 'archives de conspiration',
      occultLibraries: 'bibliothèques occultes',
      forbiddenPhilosophy: 'philosophie interdite',
      rawKnowledge: 'Connaissance brute. Accès non filtré. Places limitées disponibles.',
      joinThousands: 'Rejoins des milliers déjà éveillés à ce qu\'ils ne veulent pas que tu saches.',
      tapReveal: 'Appuie pour révéler l\'archive complète...',
      tapCollapse: 'Appuie n\'importe où pour fermer'
    },
    de: {
      title: 'Das Wissen, das sie Verbergen Wollen',
      subtitle: 'Unzensiert • Ungefiltert • Verboten',
      description: '9,000+ Bücher über okkulte Weisheit, esoterische Geheimnisse, Verschwörungen und verborgene Wahrheiten',
      occultWisdom: 'okkulte Weisheit',
      esotericSecrets: 'esoterische Geheimnisse',
      conspiracies: 'Verschwörungen',
      hiddenTruths: 'verborgene Wahrheiten',
      noCensorship: 'Keine Zensur. Keine Algorithmen, die die Wahrheit verbergen. Keine Hüter, die kontrollieren, was du lernst.',
      chatWith: 'Chatte mit Verschwörungsarchiven, okkulten Bibliotheken und verbotener Philosophie—alles, was von Mainstream-Plattformen unterdrückt wird.',
      conspircyArchives: 'Verschwörungsarchive',
      occultLibraries: 'okkulte Bibliotheken',
      forbiddenPhilosophy: 'verbotene Philosophie',
      rawKnowledge: 'Rohes Wissen. Ungefilterte Sicht. Limitierte Plätze verfügbar.',
      joinThousands: 'Tritt Tausenden bei, die bereits erwacht sind zu dem, das sie nicht wissen wollen.',
      tapReveal: 'Tippen zum Offenbaren des vollständigen Archivs...',
      tapCollapse: 'Überall tippen zum Schließen'
    },
    ru: {
      title: 'Знания, Которые Они Пытаются Скрыть',
      subtitle: 'Без Цензуры • Без Фильтров • Запрещённое',
      description: '9,000+ книг об оккультной мудрости, эзотерических секретах, заговорах и скрытых истинах',
      occultWisdom: 'оккультной мудрости',
      esotericSecrets: 'эзотерических секретах',
      conspiracies: 'заговорах',
      hiddenTruths: 'скрытых истинах',
      noCensorship: 'Никакой цензуры. Никаких алгоритмов, скрывающих правду. Никаких хранителей, контролирующих то, что ты изучаешь.',
      chatWith: 'Общайся с архивами заговоров, оккультными библиотеками и запрещённой философией—всё, что подавляется мейнстримом.',
      conspircyArchives: 'архивами заговоров',
      occultLibraries: 'оккультными библиотеками',
      forbiddenPhilosophy: 'запрещённой философией',
      rawKnowledge: 'Чистое знание. Неотфильтрованный доступ. Ограниченное количество мест.',
      joinThousands: 'Присоединяйся к тысячам уже пробудившихся к тому, что они не хотят, чтобы ты знал.',
      tapReveal: 'Нажми, чтобы открыть полный архив...',
      tapCollapse: 'Нажми где-нибудь, чтобы закрыть'
    },
    pt: {
      title: 'O Conhecimento Que Eles Tentam Esconder',
      subtitle: 'Sem Censura • Sem Filtros • Proibido',
      description: '9,000+ livros sobre sabedoria oculta, segredos esotéricos, conspirações e verdades ocultas',
      occultWisdom: 'sabedoria oculta',
      esotericSecrets: 'segredos esotéricos',
      conspiracies: 'conspirações',
      hiddenTruths: 'verdades ocultas',
      noCensorship: 'Sem censura. Sem algoritmos encobrindo a verdade. Sem guardiões controlando o que você aprende.',
      chatWith: 'Converse com arquivos de conspiração, bibliotecas ocultas e filosofia proibida—tudo suprimido por plataformas convencionais.',
      conspircyArchives: 'arquivos de conspiração',
      occultLibraries: 'bibliotecas ocultas',
      forbiddenPhilosophy: 'filosofia proibida',
      rawKnowledge: 'Conhecimento bruto. Acesso sem filtros. Lugares limitados disponíveis.',
      joinThousands: 'Junte-se a milhares já despertados para o que eles não querem que você saiba.',
      tapReveal: 'Toque para revelar o arquivo completo...',
      tapCollapse: 'Toque em qualquer lugar para fechar'
    },
    ja: {
      title: '彼らが隠そうとしている知識',
      subtitle: '無検閲 • 無フィルター • 禁止',
      description: '9,000+ 冊のオカルト知識、秘教の秘密、陰謀、隠された真実に関する本',
      occultWisdom: 'オカルト知識',
      esotericSecrets: '秘教の秘密',
      conspiracies: '陰謀',
      hiddenTruths: '隠された真実',
      noCensorship: '検閲なし。真実を隠すアルゴリズムなし。あなたの学習を制御する門番なし。',
      chatWith: '陰謀アーカイブ、オカルトライブラリ、禁止の哲学とチャット—メインストリームプラットフォームで抑圧されたすべてのもの。',
      conspircyArchives: '陰謀アーカイブ',
      occultLibraries: 'オカルトライブラリ',
      forbiddenPhilosophy: '禁止の哲学',
      rawKnowledge: '生の知識。無フィルターアクセス。限定席のみ。',
      joinThousands: 'すでに目覚めた何千人もの人々に参加して、彼らがあなたに知られたくないことを知ってください。',
      tapReveal: 'タップしてフルアーカイブを表示...',
      tapCollapse: 'どこかをタップして閉じる'
    },
    zh: {
      title: '他们试图隐藏的知识',
      subtitle: '无审查 • 无过滤 • 禁忌',
      description: '9,000+ 本关于神秘智慧、神秘秘密、阴谋和隐藏真理的书籍',
      occultWisdom: '神秘智慧',
      esotericSecrets: '神秘秘密',
      conspiracies: '阴谋',
      hiddenTruths: '隐藏真理',
      noCensorship: '无审查。没有算法掩盖真理。没有看门人控制你学什么。',
      chatWith: '与阴谋档案、神秘图书馆和禁止哲学聊天——所有被主流平台压制的东西。',
      conspircyArchives: '阴谋档案',
      occultLibraries: '神秘图书馆',
      forbiddenPhilosophy: '禁止哲学',
      rawKnowledge: '原始知识。无过滤访问。名额有限。',
      joinThousands: '加入数千个已经意识到他们不想让你知道的事情的人。',
      tapReveal: '点击查看完整档案...',
      tapCollapse: '点击任何地方关闭'
    },
    ar: {
      title: 'المعرفة التي يحاولون إخفاءها',
      subtitle: 'بدون رقابة • بدون تصفية • محظور',
      description: '9,000+ كتاب عن الحكمة الخفية والأسرار الباطنية والمؤامرات والحقائق المخفية',
      occultWisdom: 'الحكمة الخفية',
      esotericSecrets: 'الأسرار الباطنية',
      conspiracies: 'المؤامرات',
      hiddenTruths: 'الحقائق المخفية',
      noCensorship: 'لا رقابة. لا خوارزميات تخفي الحقيقة. لا حراس يتحكمون في ما تتعلمه.',
      chatWith: 'تحدث مع أرشيفات المؤامرة والمكتبات السرية والفلسفة المحظورة - كل ما تم قمعه من قبل المنصات السائدة.',
      conspircyArchives: 'أرشيفات المؤامرة',
      occultLibraries: 'المكتبات السرية',
      forbiddenPhilosophy: 'الفلسفة المحظورة',
      rawKnowledge: 'معرفة خام. وصول بدون تصفية. مقاعد محدودة متاحة.',
      joinThousands: 'انضم إلى آلاف الأشخاص الذين استيقظوا بالفعل لما لا يريدونك أن تعرفه.',
      tapReveal: 'اضغط لكشف الأرشيف الكامل...',
      tapCollapse: 'اضغط في أي مكان للإغلاق'
    }
  }

  // Get translations for current language, fallback to English
  const t = translations[userLanguage] || translations['en']

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
          text-align: center;
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
          text-align: center;
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
          text-align: center;
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
          <div className="flex flex-col items-center justify-center">
            <div className="w-full">
              <h2 className="teaser-title">
                {t.title}
              </h2>
              <p className="teaser-subtitle">
                <span className="occult-symbol">◆</span>
                {t.subtitle}
                <span className="occult-symbol">◆</span>
              </p>
              <p className="text-gray-400 text-sm mt-3 leading-relaxed text-center">
                9,000+ {t.description.split('on ')[1]}
              </p>
            </div>
            <svg
              className={`expand-icon ${isExpanded ? 'expanded' : ''} w-6 h-6 text-cyan-400 mt-3`}
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
                  {t.noCensorship}
                </p>
                <p>
                  {t.chatWith.split('conspiracy archives')[0]}<span className="knowledge-highlight">{t.conspircyArchives}</span>{t.chatWith.split('conspiracy archives')[1].split('occult libraries')[0]}<span className="knowledge-highlight">{t.occultLibraries}</span>{t.chatWith.split('conspiracy archives')[1].split('occult libraries')[1].split('forbidden philosophy')[0]}<span className="knowledge-highlight">{t.forbiddenPhilosophy}</span>{t.chatWith.split('conspiracy archives')[1].split('occult libraries')[1].split('forbidden philosophy')[1]}
                </p>
                <p className="text-cyan-300/80 font-semibold">
                  {t.rawKnowledge}
                </p>
                <p className="text-purple-300/70 text-sm pt-2">
                  {t.joinThousands}
                </p>
              </div>
            </div>
          )}

          {/* CTA Section */}
          {isExpanded && (
            <div className="mt-4 pt-3 border-t border-cyan-500/20">
              <p className="text-xs text-gray-500 mb-3">
                {t.tapCollapse}
              </p>
            </div>
          )}

          {/* Always visible hint */}
          {!isExpanded && (
            <p className="text-xs text-cyan-400/60 mt-3 animate-pulse">
              {t.tapReveal}
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
