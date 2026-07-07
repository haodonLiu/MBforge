import StorageSection from '@/components/settings/StorageSection'

interface Props {
  projectRoot: string
}

export default function CacheTab({ projectRoot }: Props) {
  return <StorageSection projectRoot={projectRoot} />
}
