import { create } from 'zustand'
import type { Conversation, Message, PDF, Source } from '@/types'
import { api } from '@/lib/api'

interface ChatState {
  // State
  conversations: Conversation[]
  currentConversation: Conversation | null
  availablePdfs: PDF[]
  selectedPdfIds: string[]
  isLoadingPdfs: boolean
  isLoadingConversations: boolean
  isSending: boolean
  streamingContent: string

  // Actions
  loadPdfs: () => Promise<void>
  loadConversations: () => Promise<void>
  loadFullConversation: (conversationId: string) => Promise<void>
  selectPdf: (pdfId: string) => void
  deselectPdf: (pdfId: string) => void
  selectAllPdfs: () => void
  clearPdfSelection: () => void
  setSelectedPdfIds: (pdfIds: string[]) => void
  setCurrentConversation: (conversation: Conversation | null) => void
  createConversation: () => Promise<Conversation | null>
  deleteConversation: (id: string) => Promise<void>
  sendMessage: (content: string) => Promise<void>
  clearStreamingContent: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversation: null,
  availablePdfs: [],
  selectedPdfIds: [],
  isLoadingPdfs: false,
  isLoadingConversations: false,
  isSending: false,
  streamingContent: '',

  loadPdfs: async () => {
    console.log('🔄 loadPdfs() called - starting to load documents')
    set({ isLoadingPdfs: true })
    try {
      // Use getDocuments instead of getPDFs to get actual individual documents with titles
      // getPDFs returns collections, but we need documents with their full titles
      console.log('📡 Fetching documents from /api/telegram/documents')
      // Try with default parameters first (page=1, per_page=20)
      // Then increase per_page to 500 (max allowed)
      const result = await api.getDocuments(1, 500, 'all') // Max per_page is 500
      console.log('📦 API response:', result)
      if (result.success && result.data?.documents) {
        // Transform to PDF format
        console.log(`📄 Transforming ${result.data.documents.length} documents`)
        const pdfs = result.data.documents.map((doc: any) => ({
          id: doc.id,
          title: doc.title,
          description: doc.filename || 'Unknown',
          category: doc.collection || 'Unknown',
          pageCount: doc.page_count,
          createdAt: new Date().toISOString(),
          cover_url: doc.cover_url, // Include cover URL from response
        }))

        // Don't auto-select PDFs here - let the URL params effect handle selection
        // This allows ?docs=maglib:123 to work correctly
        set({
          availablePdfs: pdfs
          // Don't touch selectedPdfIds - let URL params effect set it
        })
        console.log(`✅ Loaded ${pdfs.length} documents for chat`)
      } else {
        console.warn('⚠️ API response missing success or documents:', result)
      }
    } catch (error) {
      console.error('❌ Failed to load documents:', error)
    }
    set({ isLoadingPdfs: false })
  },

  loadConversations: async () => {
    set({ isLoadingConversations: true })
    const result = await api.getConversations()
    if (result.success && result.data) {
      set({ conversations: result.data })
    }
    set({ isLoadingConversations: false })
  },

  loadFullConversation: async (conversationId: string) => {
    const result = await api.getConversation(conversationId)
    if (result.success && result.data) {
      const loadedConversation = result.data
      // CRITICAL: Merge loaded data with current state instead of replacing
      // This preserves streaming messages that are being updated in real-time
      set(state => {
        if (!state.currentConversation) return { currentConversation: loadedConversation }

        // Keep the current messages (which may have streaming content) but update pdfIds
        return {
          currentConversation: {
            ...state.currentConversation,
            ...loadedConversation,
            // IMPORTANT: Preserve current messages if they're more recent/complete than loaded messages
            messages: state.currentConversation.messages.length > 0
              ? state.currentConversation.messages
              : loadedConversation.messages || [],
          }
        }
      })
    }
  },

  selectPdf: (pdfId: string) => {
    const { selectedPdfIds } = get()
    if (!selectedPdfIds.includes(pdfId)) {
      set({ selectedPdfIds: [...selectedPdfIds, pdfId] })
    }
  },

  deselectPdf: (pdfId: string) => {
    const { selectedPdfIds } = get()
    set({ selectedPdfIds: selectedPdfIds.filter(id => id !== pdfId) })
  },

  selectAllPdfs: () => {
    const { availablePdfs } = get()
    set({ selectedPdfIds: availablePdfs.map(pdf => pdf.id) })
  },

  clearPdfSelection: () => {
    set({ selectedPdfIds: [] })
  },

  setSelectedPdfIds: (pdfIds: string[]) => {
    set({ selectedPdfIds: pdfIds })
  },

  setCurrentConversation: (conversation) => {
    // CRITICAL: Update both currentConversation and selectedPdfIds in a single atomic update
    // This prevents race conditions when switching between documents
    set(state => ({
      currentConversation: conversation,
      selectedPdfIds: conversation ? conversation.pdfIds : state.selectedPdfIds,
    }))
  },

  createConversation: async () => {
    const { selectedPdfIds } = get()
    if (selectedPdfIds.length === 0) return null

    const result = await api.createConversation(selectedPdfIds)
    if (result.success && result.data) {
      set(state => ({
        conversations: [result.data!, ...state.conversations],
        currentConversation: result.data!,
      }))
      return result.data
    }
    return null
  },

  deleteConversation: async (id: string) => {
    await api.deleteConversation(id)
    set(state => ({
      conversations: state.conversations.filter(c => c.id !== id),
      currentConversation: state.currentConversation?.id === id ? null : state.currentConversation,
    }))
  },

  sendMessage: async (content: string) => {
    const { currentConversation, selectedPdfIds } = get()
    if (!content.trim()) return

    set({ isSending: true, streamingContent: '' })

    // Add user message immediately
    const userMessage: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: content.trim(),
      timestamp: new Date().toISOString(),
    }

    // Add placeholder for assistant response
    const assistantMessage: Message = {
      id: `temp-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isStreaming: true,
    }

    set(state => ({
      currentConversation: state.currentConversation ? {
        ...state.currentConversation,
        messages: [...state.currentConversation.messages, userMessage, assistantMessage],
      } : null,
    }))

    // Stream the response
    let fullContent = ''
    let sources: Source[] = []

    // Only send real conversation IDs (not temporary "new-" IDs)
    const realConversationId = currentConversation?.id?.startsWith('new-')
      ? undefined
      : currentConversation?.id

    // Determine which collection(s) are in selectedPdfIds
    const collections = new Set<string>()
    selectedPdfIds.forEach(id => {
      if (id.startsWith('bibliothek:')) {
        collections.add('bibliothek')
      } else if (id.startsWith('maglib:')) {
        collections.add('maglib')
      }
    })

    // Determine which collection to send to backend
    // If all documents are from same collection, send that collection
    // If mixed, default to maglib (backend will handle document_ids filtering)
    const collection = collections.size === 1 ? Array.from(collections)[0] : 'maglib'

    await api.streamMessage(
      {
        conversationId: realConversationId,
        message: content.trim(),
        pdfIds: selectedPdfIds,
        collection,
      },
      // On chunk
      (chunk: string) => {
        fullContent += chunk
        set({ streamingContent: fullContent })

        // Update the assistant message in real-time
        set(state => {
          if (!state.currentConversation) return state
          const messages = [...state.currentConversation.messages]
          const lastMessage = messages[messages.length - 1]
          if (lastMessage && lastMessage.role === 'assistant') {
            messages[messages.length - 1] = { ...lastMessage, content: fullContent }
          }
          return {
            currentConversation: {
              ...state.currentConversation,
              messages,
            },
          }
        })
      },
      // On done
      (responseSources) => {
        sources = responseSources || []

        // Finalize the assistant message
        set(state => {
          if (!state.currentConversation) return state
          const messages = [...state.currentConversation.messages]
          const lastMessage = messages[messages.length - 1]
          if (lastMessage && lastMessage.role === 'assistant') {
            messages[messages.length - 1] = {
              ...lastMessage,
              content: fullContent,
              sources,
              isStreaming: false,
            }
          }
          return {
            currentConversation: {
              ...state.currentConversation,
              messages,
            },
            isSending: false,
            streamingContent: '',
          }
        })
      },
      // On error
      (error: string) => {
        console.error('Chat error:', error)
        set(state => {
          if (!state.currentConversation) return state
          const messages = [...state.currentConversation.messages]
          const lastMessage = messages[messages.length - 1]
          if (lastMessage && lastMessage.role === 'assistant') {
            messages[messages.length - 1] = {
              ...lastMessage,
              content: `Error: ${error}`,
              isStreaming: false,
            }
          }
          return {
            currentConversation: {
              ...state.currentConversation,
              messages,
            },
            isSending: false,
            streamingContent: '',
          }
        })
      },
      // On conversation ID - CRITICAL for conversation memory
      async (newConversationId: string) => {
        // Update temporary "new-" ID with real backend ID
        // This enables subsequent messages to use the same conversation thread
        set(state => {
          if (!state.currentConversation) return state
          // Only update if current ID is temporary
          if (state.currentConversation.id?.startsWith('new-')) {
            console.log(`Conversation ID updated: ${state.currentConversation.id} -> ${newConversationId}`)
            return {
              currentConversation: {
                ...state.currentConversation,
                id: newConversationId,
              },
            }
          }
          return state
        })

        // CRITICAL: Load full conversation with messages from backend
        // This ensures conversation history is available for follow-up messages
        // MUST await this to prevent race condition where next message is sent before history loads
        await get().loadFullConversation(newConversationId)
      }
    )
  },

  clearStreamingContent: () => {
    set({ streamingContent: '' })
  },
}))
