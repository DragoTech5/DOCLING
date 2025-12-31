import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'

// Pages
import HomePage from '@/pages/HomePage'
import ChatPage from '@/pages/ChatPage'
import PricingPage from '@/pages/PricingPage'
import HistoryPage from '@/pages/HistoryPage'
import ArchivePage from '@/pages/ArchivePage'
import SharePage from '@/pages/SharePage'
import AdminPage from '@/pages/AdminPage'
import PaymentSuccessPage from '@/pages/PaymentSuccessPage'
import PaymentFailurePage from '@/pages/PaymentFailurePage'

// Components
import LoadingScreen from '@/components/LoadingScreen'

function App() {
  const { initialize, isInitialized, isLoading } = useAuthStore()
  const { loadPdfs, loadConversations } = useChatStore()

  useEffect(() => {
    // Initialize auth and load initial data
    initialize().then(() => {
      loadPdfs()
      loadConversations()
    })
  }, [initialize, loadPdfs, loadConversations])

  if (!isInitialized || isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="min-h-screen bg-dark text-gray-100 flex flex-col">
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/archive" element={<ArchivePage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:conversationId" element={<ChatPage />} />
        <Route path="/share/:shareToken" element={<SharePage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/payment-success" element={<PaymentSuccessPage />} />
        <Route path="/payment-failure" element={<PaymentFailurePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default App
