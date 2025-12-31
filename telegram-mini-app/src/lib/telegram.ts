// Telegram WebApp utilities

export function getTelegramWebApp() {
  return window.Telegram?.WebApp
}

export function getTelegramUser() {
  const tg = getTelegramWebApp()
  return tg?.initDataUnsafe?.user
}

export function getInitData() {
  return getTelegramWebApp()?.initData || ''
}

export function hapticFeedback(type: 'light' | 'medium' | 'heavy' | 'success' | 'error' | 'warning' | 'selection') {
  const tg = getTelegramWebApp()
  if (!tg?.HapticFeedback) return

  if (type === 'selection') {
    tg.HapticFeedback.selectionChanged()
  } else if (['success', 'error', 'warning'].includes(type)) {
    tg.HapticFeedback.notificationOccurred(type as 'success' | 'error' | 'warning')
  } else {
    tg.HapticFeedback.impactOccurred(type as 'light' | 'medium' | 'heavy')
  }
}

export function showMainButton(text: string, onClick: () => void) {
  const tg = getTelegramWebApp()
  if (!tg?.MainButton) return

  tg.MainButton.setText(text)
  tg.MainButton.onClick(onClick)
  tg.MainButton.show()
}

export function hideMainButton() {
  const tg = getTelegramWebApp()
  tg?.MainButton?.hide()
}

export function setMainButtonLoading(loading: boolean) {
  const tg = getTelegramWebApp()
  if (!tg?.MainButton) return

  if (loading) {
    tg.MainButton.showProgress()
    tg.MainButton.disable()
  } else {
    tg.MainButton.hideProgress()
    tg.MainButton.enable()
  }
}

export function showBackButton(onClick: () => void) {
  const tg = getTelegramWebApp()
  if (!tg?.BackButton) return

  tg.BackButton.onClick(onClick)
  tg.BackButton.show()
}

export function hideBackButton() {
  const tg = getTelegramWebApp()
  tg?.BackButton?.hide()
}

export function openInvoice(url: string): Promise<'paid' | 'cancelled' | 'failed' | 'pending'> {
  return new Promise((resolve) => {
    const tg = getTelegramWebApp()
    if (!tg?.openInvoice) {
      resolve('failed')
      return
    }
    tg.openInvoice(url, (status: 'paid' | 'cancelled' | 'failed' | 'pending') => {
      resolve(status)
    })
  })
}

export function showAlert(message: string): Promise<void> {
  return new Promise((resolve) => {
    const tg = getTelegramWebApp()
    if (!tg?.showAlert) {
      alert(message)
      resolve()
      return
    }
    tg.showAlert(message, () => resolve())
  })
}

export function showConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    const tg = getTelegramWebApp()
    if (!tg?.showConfirm) {
      resolve(confirm(message))
      return
    }
    tg.showConfirm(message, (confirmed: boolean) => resolve(confirmed))
  })
}

// Cloud storage helpers
export function cloudStorageSet(key: string, value: string): Promise<boolean> {
  return new Promise((resolve) => {
    const tg = getTelegramWebApp()
    if (!tg?.CloudStorage) {
      try {
        localStorage.setItem(key, value)
        resolve(true)
      } catch {
        resolve(false)
      }
      return
    }
    tg.CloudStorage.setItem(key, value, (error: string | null, stored: boolean) => {
      resolve(!error && stored)
    })
  })
}

export function cloudStorageGet(key: string): Promise<string | null> {
  return new Promise((resolve) => {
    const tg = getTelegramWebApp()
    if (!tg?.CloudStorage) {
      resolve(localStorage.getItem(key))
      return
    }
    tg.CloudStorage.getItem(key, (error: string | null, value: string) => {
      resolve(error ? null : value)
    })
  })
}

export function cloudStorageRemove(key: string): Promise<boolean> {
  return new Promise((resolve) => {
    const tg = getTelegramWebApp()
    if (!tg?.CloudStorage) {
      try {
        localStorage.removeItem(key)
        resolve(true)
      } catch {
        resolve(false)
      }
      return
    }
    tg.CloudStorage.removeItem(key, (error: string | null, removed: boolean) => {
      resolve(!error && removed)
    })
  })
}

export function setHeaderColor(color: string) {
  getTelegramWebApp()?.setHeaderColor(color)
}

export function setBackgroundColor(color: string) {
  getTelegramWebApp()?.setBackgroundColor(color)
}

export function closeMiniApp() {
  getTelegramWebApp()?.close()
}
