import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'
import { api } from './lib/api'

// Get Telegram WebApp instance and initialize
const tg = window.Telegram?.WebApp

if (tg) {
  // Signal that the app is ready
  tg.ready()
  // Expand to full height
  tg.expand()
  // Enable closing confirmation (prevent accidental closes)
  tg.enableClosingConfirmation()
  // Set the init data for API authentication
  if (tg.initData) {
    api.setInitData(tg.initData)
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename="/twa">
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
