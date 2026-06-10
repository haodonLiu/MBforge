interface TagPillProps {
  label: string
  active: boolean
  onClick: () => void
}

export default function TagPill({ label, active, onClick }: TagPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="notes-tag-pill"
      data-active={active}
    >
      #{label}
    </button>
  )
}
