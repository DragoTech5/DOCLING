import type {
  ApiResponse,
  UserProfile,
  PDF,
  Conversation,
  ChatRequest,
  ChatResponse,
  SubscriptionInvoice,
  SubscriptionTier
} from '@/types'

// Use relative URLs when accessed through tunnel/proxy, absolute for local dev
const API_URL = import.meta.env.VITE_API_URL ||
  (typeof window !== 'undefined' && window.location.hostname !== 'localhost' ? '' : 'http://localhost:8200')

class ApiClient {
  private initData: string = ''

  setInitData(initData: string) {
    this.initData = initData
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(this.initData && { 'X-Telegram-Init-Data': this.initData }),
      ...options.headers,
    }

    try {
      const response = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Request failed' }))
        return { success: false, error: error.error || error.detail || 'Request failed' }
      }

      const data = await response.json()
      return { success: true, data }
    } catch (error) {
      console.error('API request failed:', error)
      return { success: false, error: 'Network error. Please try again.' }
    }
  }

  // Auth endpoints
  async authenticate(): Promise<ApiResponse<UserProfile>> {
    return this.request<UserProfile>('/api/telegram/auth', {
      method: 'POST',
    })
  }

  async getProfile(): Promise<ApiResponse<UserProfile>> {
    return this.request<UserProfile>('/api/telegram/profile')
  }

  // PDF endpoints (old ChromaDB - kept for compatibility)
  async getPDFs(): Promise<ApiResponse<PDF[]>> {
    return this.request<PDF[]>('/api/telegram/pdfs')
  }

  // Documents endpoints (pgvector - Knowledge Archive)
  async getDocuments(page: number = 1, per_page: number = 20, collection: string = 'all', search?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: per_page.toString(),
      collection,
    })
    if (search) params.append('search', search)
    return this.request<any>(`/api/telegram/documents?${params}`)
  }

  // Conversation endpoints
  async getConversations(): Promise<ApiResponse<Conversation[]>> {
    return this.request<Conversation[]>('/api/telegram/conversations')
  }

  async getConversation(id: string): Promise<ApiResponse<Conversation>> {
    return this.request<Conversation>(`/api/telegram/conversations/${id}`)
  }

  async createConversation(pdfIds: string[]): Promise<ApiResponse<Conversation>> {
    return this.request<Conversation>('/api/telegram/conversations', {
      method: 'POST',
      body: JSON.stringify({ pdfIds }),
    })
  }

  async deleteConversation(id: string): Promise<ApiResponse<void>> {
    return this.request<void>(`/api/telegram/conversations/${id}`, {
      method: 'DELETE',
    })
  }

  // Chat endpoints
  async sendMessage(request: ChatRequest): Promise<ApiResponse<ChatResponse>> {
    return this.request<ChatResponse>('/api/telegram/chat', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  }

  // Streaming chat
  async streamMessage(
    request: ChatRequest,
    onChunk: (chunk: string) => void,
    onDone: (sources: ChatResponse['message']['sources']) => void,
    onError: (error: string) => void,
    onConversationId?: (conversationId: string) => void | Promise<void>
  ): Promise<void> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(this.initData && { 'X-Telegram-Init-Data': this.initData }),
    }

    try {
      const response = await fetch(`${API_URL}/api/telegram/chat/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify(request),
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Request failed' }))
        onError(error.error || 'Request failed')
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('Stream not supported')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              continue
            }
            try {
              const parsed = JSON.parse(data)
              if (parsed.type === 'conversation_id') {
                // CRITICAL: Backend sends conversation_id first for conversation memory
                // MUST await if async to prevent race condition with chunk processing
                const result = onConversationId?.(parsed.conversationId)
                if (result instanceof Promise) {
                  await result
                }
              } else if (parsed.type === 'chunk') {
                onChunk(parsed.content)
              } else if (parsed.type === 'sources') {
                onDone(parsed.sources)
              } else if (parsed.type === 'error') {
                onError(parsed.message)
              }
            } catch {
              // Skip non-JSON lines
            }
          }
        }
      }
    } catch (error) {
      console.error('Stream error:', error)
      onError('Connection lost. Please try again.')
    }
  }

  // Subscription endpoints
  async createSubscriptionInvoice(tier: SubscriptionTier): Promise<ApiResponse<SubscriptionInvoice>> {
    return this.request<SubscriptionInvoice>('/api/telegram/subscribe', {
      method: 'POST',
      body: JSON.stringify({ tier }),
    })
  }

  async purchaseTokenBundle(bundleId: string): Promise<ApiResponse<SubscriptionInvoice>> {
    return this.request<SubscriptionInvoice>('/api/telegram/purchase-tokens', {
      method: 'POST',
      body: JSON.stringify({ bundleId }),
    })
  }
}

export const api = new ApiClient()
