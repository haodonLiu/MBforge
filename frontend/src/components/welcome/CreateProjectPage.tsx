import { motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { ArrowLeftIcon } from '../icons'
import { slideFromRight } from '../../hooks/useAnimations'
import Button from '../ui/Button'
import Input from '../ui/Input'
import Caption from '../ui/Caption'
import Spinner from '../ui/Spinner'
import { FolderPicker } from '../ui/FolderPicker'
import { sanitizePath } from './utils'

interface CreateProjectPageProps {
  selectedDir: string
  projectName: string
  loading: boolean
  onDirChange: (path: string) => void
  onNameChange: (name: string) => void
  onCreate: () => void
  onCancel: () => void
}

export default function CreateProjectPage({
  selectedDir,
  projectName,
  loading,
  onDirChange,
  onNameChange,
  onCreate,
  onCancel,
}: CreateProjectPageProps) {
  const { t } = useTranslation()

  return (
    <motion.div
      variants={slideFromRight}
      initial="hidden"
      animate="visible"
      exit="exit"
      className="welcome-subpage"
    >
      <div className="welcome-subpage-inner">
        <div className="welcome-subpage-back">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <ArrowLeftIcon size={16} /> {t('common.cancel')}
          </Button>
        </div>

        <h2 className="welcome-subpage-title">{t('welcome.createProject')}</h2>

        <div className="welcome-form-group">
          <label className="welcome-form-label">{t('welcome.selectFolder')}</label>
          <FolderPicker
            value={selectedDir}
            onChange={(path) => onDirChange(sanitizePath(path))}
            placeholder={t('welcome.selectFolder')}
            title={t('welcome.selectFolder')}
          />
        </div>

        <div className="welcome-form-group">
          <label className="welcome-form-label">{t('welcome.projectName')}</label>
          <Input
            value={projectName}
            onChange={e => onNameChange(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && onCreate()}
            placeholder={t('welcome.projectNamePlaceholder')}
            autoFocus
          />
        </div>

        {selectedDir && projectName && (
          <div className="welcome-form-preview">
            <Caption>{t('welcome.create')}: <strong>{selectedDir}/{projectName}</strong></Caption>
          </div>
        )}

        <Button
          variant="primary"
          size="lg"
          disabled={loading || !selectedDir.trim() || !projectName.trim()}
          onClick={onCreate}
        >
          {loading ? (
            <>
              <Spinner size={14} color="currentColor" />
              {t('common.loading')}
            </>
          ) : t('welcome.create')}
        </Button>
      </div>
    </motion.div>
  )
}
