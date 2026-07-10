import StorageSection from '@/components/settings/StorageSection'

interface Props {
  libraryRoot: string
}

export default function CacheTab({ libraryRoot }: Props) {
  return <StorageSection libraryRoot={libraryRoot} />
}
