import AlertBanner from './ui/AlertBanner'

interface ErrorBannerProps {
  message: string
  onDismiss?: () => void
}

export default function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  if (!message) return null
  return <AlertBanner variant="danger" message={message} onDismiss={onDismiss} />
}
