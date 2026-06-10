import { motion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { ArrowLeftIcon } from '../icons'
import { slideFromRight } from '../../hooks/useAnimations'
import Button from '../ui/Button'
import Spinner from '../ui/Spinner'
import { FolderPicker } from '../ui/FolderPicker'
import { sanitizePath } from './utils'

interface OpenProjectPageProps {
  selectedDir: string
  loading: boolean
  onDirChange: (path: string) => void
  onOpen: () => void
  onCancel: () => void
}

export default function OpenProjectPage({
  selectedDir,
  loading,
  onDirChange,
  onOpen,
  onCancel,
}: OpenProjectPageProps) {
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

        <h2 className="welcome-subpage-title">{t('welcome.openProject')}</h2>

        <div className="welcome-form-group">
          <label className="welcome-form-label">{t('common.project')}</label>
          <FolderPicker
            value={selectedDir}
            onChange={(path) => onDirChange(sanitizePath(path))}
            placeholder={t('welcome.selectFolder')}
            title={t('welcome.openProject')}
          />
        </div>

        <Button
          variant="primary"
          size="lg"
          disabled={loading || !selectedDir.trim()}
          onClick={onOpen}
        >
          {loading ? (
            <>
              <Spinner size={14} color="currentColor" />
              {t('common.loading')}
            </>
          ) : t('welcome.openProject')}
        </Button>
      </div>
    </motion.div>
  )
}
