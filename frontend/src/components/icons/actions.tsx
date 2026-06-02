/**
 * 操作类图标：编辑、删除、发送、确认等
 */
import type { FC } from 'react'
import { baseSvg, type IconProps } from './types'

export const PlusIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </>,
    size,
  )

export const XIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </>,
    size,
  )

export const CheckIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <polyline points="20 6 9 17 4 12" />
    </>,
    size,
  )

export const SendIcon: FC<IconProps> = ({ size = 18 }) =>
  baseSvg(
    <>
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </>,
    size,
  )

export const TrashIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </>,
    size,
  )

export const DownloadIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </>,
    size,
  )

export const UploadIcon: FC<IconProps> = ({ size = 40 }) =>
  baseSvg(
    <>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </>,
    size,
  )

export const EditIcon: FC<IconProps> = ({ size = 14 }) =>
  baseSvg(
    <>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </>,
    size,
  )

export const CopyIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </>,
    size,
  )

export const RefreshCwIcon: FC<IconProps> = ({ size = 14 }) =>
  baseSvg(
    <>
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </>,
    size,
  )
