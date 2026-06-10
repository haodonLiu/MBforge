import { useTranslation } from 'react-i18next'
import { TextArea, IconButton, Button } from '../ui'
import { SendIcon, FlaskIcon } from '../icons'

interface ChatInputProps {
  input: string
  onInputChange: (v: string) => void
  onSend: () => void
  isLoading: boolean
  projectRoot: string | null
}

export default function ChatInput({ input, onInputChange, onSend, isLoading, projectRoot }: ChatInputProps) {
  const { t } = useTranslation()

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  const insertTemplate = (template: string) => {
    const templates: Record<string, string> = {
      search_mol: t('chat.searchMolPrefix'),
      analyze_sar: t('chat.analyzeSarPrefix'),
      dock: t('chat.dockPrefix'),
    }
    onInputChange(input + (templates[template] || ''))
  }

  return (
    <div className="chat-input-area">
      <div className="chat-quick-actions">
        <Button variant="ghost" size="sm" onClick={() => insertTemplate('search_mol')}>
          <FlaskIcon size={13} /> {t('chat.searchMolecule')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => insertTemplate('analyze_sar')}>
          <FlaskIcon size={13} /> {t('chat.sarAnalysis')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => insertTemplate('dock')}>
          <FlaskIcon size={13} /> {t('chat.molecularDocking')}
        </Button>
      </div>

      <div className="chat-input-box">
        <TextArea
          value={input}
          onChange={e => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={projectRoot ? t('chat.placeholder') : t('chat.placeholderNoProject')}
          maxHeight="120px"
          disabled={isLoading || !projectRoot}
          rows={1}
        />
        <IconButton
          size={36}
          disabled={!input.trim() || isLoading || !projectRoot}
          onClick={onSend}
        >
          <SendIcon size={16} />
        </IconButton>
      </div>
    </div>
  )
}
