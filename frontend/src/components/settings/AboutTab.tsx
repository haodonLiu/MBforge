import AboutSection from '@/components/settings/sections/AboutSection'

interface Props {
  onReset: () => void
  onOpenConfig: () => void
}

export default function AboutTab({ onReset, onOpenConfig }: Props) {
  return <AboutSection onReset={onReset} onOpenConfig={onOpenConfig} />
}
