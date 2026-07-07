/**
 * Icons — all icon components merged from sub-domain files.
 *
 * Categories (kept as comment groupings for findability):
 * - Nav: FolderIcon, FolderOpenIcon, FileTextIcon, PdfIcon, LayoutIcon, EnvironmentIcon
 * - Actions: PlusIcon, XIcon, CheckIcon, SendIcon, TrashIcon, DownloadIcon, UploadIcon,
 *            EditIcon, CopyIcon, RefreshCwIcon, EyeIcon, EyeOffIcon, PinIcon, UnpinIcon
 * - UI: SearchIcon, SettingsIcon, ChatIcon, UserIcon, BotIcon, HelpIcon, InfoIcon,
 *       AlertIcon, GlobeIcon, HashIcon, ClockIcon, NoteIcon, CpuIcon, QueueIcon,
 *       TableIcon, GridIcon, ChevronDownIcon, ChevronUpIcon
 * - Arrows: ChevronRightIcon, ChevronLeftIcon, ArrowLeftIcon, ExternalLinkIcon
 * - Science: FlaskIcon, SparklesIcon, TargetIcon, BarChartIcon, ClusterIcon,
 *            NetworkIcon, FilterIcon, EmbedIcon
 * - Brand: MoleculeLogo
 */

import type { FC } from 'react'
import { baseSvg, type IconProps } from './types'

// ──────────────────────────────────────────────
// Nav
// ──────────────────────────────────────────────

export const FolderIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </>,
    size,
  )

export const FolderOpenIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2z" />
    </>,
    size,
  )

export const FileTextIcon: FC<IconProps> = ({ size = 14 }) =>
  baseSvg(
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </>,
    size,
  )

export const PdfIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </>,
    size,
  )

export const LayoutIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="9" y1="21" x2="9" y2="9" />
    </>,
    size,
  )

export const EnvironmentIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <rect x="3" y="3" width="6" height="6" rx="1" />
      <rect x="15" y="15" width="6" height="6" rx="1" />
      <path d="M9 6h7a2 2 0 0 1 2 2v7" />
    </>,
    size,
  )

// ──────────────────────────────────────────────
// Actions
// ──────────────────────────────────────────────

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
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
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
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </>,
    size,
  )

export const CopyIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <rect x="9" y="9" width="13" height="13" rx="2" />
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

export const EyeIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </>,
    size,
  )

export const EyeOffIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </>,
    size,
  )

export const PinIcon: FC<IconProps> = ({ size = 14 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="1" />
    </>,
    size,
  )

export const UnpinIcon: FC<IconProps> = ({ size = 14 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="10" fill="none" />
      <line x1="8" y1="12" x2="16" y2="12" />
    </>,
    size,
  )

// ──────────────────────────────────────────────
// UI
// ──────────────────────────────────────────────

export const SearchIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </>,
    size,
  )

export const SettingsIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </>,
    size,
  )

export const ChatIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </>,
    size,
  )

export const UserIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </>,
    size,
  )

export const BotIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <circle cx="8" cy="14" r="1" />
      <circle cx="16" cy="14" r="1" />
      <path d="M12 3v4M8 3l2 2M16 3l-2 2" />
    </>,
    size,
  )

export const HelpIcon: FC<IconProps> = ({ size = 18 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </>,
    size,
  )

export const InfoIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </>,
    size,
  )

export const AlertIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </>,
    size,
  )

export const GlobeIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </>,
    size,
  )

export const HashIcon: FC<IconProps> = ({ size = 14 }) =>
  baseSvg(
    <>
      <line x1="4" y1="9" x2="20" y2="9" />
      <line x1="4" y1="15" x2="20" y2="15" />
      <line x1="10" y1="3" x2="8" y2="21" />
      <line x1="16" y1="3" x2="14" y2="21" />
    </>,
    size,
  )

export const ClockIcon: FC<IconProps> = ({ size = 14 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </>,
    size,
  )

export const NoteIcon: FC<IconProps> = ({ size = 14 }) =>
  baseSvg(
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </>,
    size,
  )

export const CpuIcon: FC<IconProps> = ({ size = 18 }) =>
  baseSvg(
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
      <line x1="9" y1="1" x2="9" y2="4" />
      <line x1="15" y1="1" x2="15" y2="4" />
      <line x1="9" y1="20" x2="9" y2="23" />
      <line x1="15" y1="20" x2="15" y2="23" />
      <line x1="20" y1="9" x2="23" y2="9" />
      <line x1="20" y1="14" x2="23" y2="14" />
      <line x1="1" y1="9" x2="4" y2="9" />
      <line x1="1" y1="14" x2="4" y2="14" />
    </>,
    size,
  )

export const QueueIcon: FC<IconProps> = ({ size = 18 }) =>
  baseSvg(
    <>
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </>,
    size,
  )

export const TableIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="12" y1="4" x2="12" y2="20" />
    </>,
    size,
  )

export const GridIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
    </>,
    size,
  )

export const ChevronDownIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <polyline points="6 9 12 15 18 9" />
    </>,
    size,
  )

export const ChevronUpIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <polyline points="6 15 12 9 18 15" />
    </>,
    size,
  )

// ──────────────────────────────────────────────
// Arrows
// ──────────────────────────────────────────────

export const ChevronRightIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <polyline points="9 18 15 12 9 6" />
    </>,
    size,
  )

export const ChevronLeftIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <polyline points="15 18 9 12 15 6" />
    </>,
    size,
  )

export const ArrowLeftIcon: FC<IconProps> = ({ size = 18 }) =>
  baseSvg(
    <>
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </>,
    size,
  )

export const ExternalLinkIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </>,
    size,
  )

// ──────────────────────────────────────────────
// Science
// ──────────────────────────────────────────────

export const FlaskIcon: FC<IconProps> = ({ size = 20 }) =>
  baseSvg(
    <>
      <path d="M9 3h6v5l4 11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L9 8V3" />
      <line x1="9" y1="3" x2="15" y2="3" />
      <line x1="7" y1="14" x2="17" y2="14" />
    </>,
    size,
  )

export const SparklesIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
      <path d="M18 15l-1 2.5L14.5 18l2.5 1 1 2.5 1-2.5L22 18l-2.5-1L18 15z" />
    </>,
    size,
  )

export const TargetIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </>,
    size,
  )

export const BarChartIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </>,
    size,
  )

export const ClusterIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="8" cy="8" r="4" />
      <circle cx="16" cy="12" r="4" />
      <circle cx="8" cy="18" r="4" />
      <line x1="11" y1="10" x2="12.5" y2="10.5" />
      <line x1="12" y1="14" x2="12.5" y2="13" />
    </>,
    size,
  )

export const NetworkIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="7" cy="4" r="2" />
      <circle cx="17" cy="4" r="2" />
      <circle cx="7" cy="20" r="2" />
      <circle cx="17" cy="20" r="2" />
      <line x1="9" y1="5" x2="15" y2="5" />
      <line x1="7" y1="6" x2="7" y2="18" />
      <line x1="17" y1="6" x2="17" y2="18" />
      <line x1="9" y1="19" x2="15" y2="19" />
    </>,
    size,
  )

export const FilterIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <polygon points="3 5 12 14 12 20 15 20 15 14 21 5" />
    </>,
    size,
  )

export const EmbedIcon: FC<IconProps> = ({ size = 16 }) =>
  baseSvg(
    <>
      <circle cx="8" cy="8" r="3" />
      <circle cx="18" cy="8" r="3" />
      <circle cx="13" cy="18" r="3" />
      <line x1="10.5" y1="9.5" x2="15.5" y2="15.5" />
      <line x1="17" y1="10" x2="14" y2="15" />
      <line x1="10.5" y1="14.5" x2="10" y2="15" />
      <line x1="17" y1="6" x2="17" y2="5" />
    </>,
    size,
  )

// ──────────────────────────────────────────────
// Brand
// ──────────────────────────────────────────────

export const MoleculeLogo: FC<IconProps> = ({ size = 72 }) => (
  <svg width={size} height={size} viewBox="0 0 72 72" fill="none">
    <defs>
      <linearGradient id="mblogo-bg" x1="0" y1="0" x2="72" y2="72" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="#0f0f1e" />
        <stop offset="1" stopColor="#1a1a2e" />
      </linearGradient>
    </defs>
    <rect width="72" height="72" rx="16" fill="url(#mblogo-bg)" />
    <polygon points="36,24 46.4,30 46.4,42 36,48 25.6,42 25.6,30" stroke="#9ca3af" strokeWidth={2} strokeLinejoin="round" opacity={0.75} />
    <polygon points="36,16 42.9,20 42.9,28 36,32 29.1,28 29.1,20" stroke="#38bdf8" strokeWidth={2.5} strokeLinejoin="round" />
    <polygon points="46.4,34 53.3,38 53.3,46 46.4,50 39.5,46 39.5,38" stroke="#a78bfa" strokeWidth={2.5} strokeLinejoin="round" />
    <polygon points="25.6,34 32.5,38 32.5,46 25.6,50 18.7,46 18.7,38" stroke="#818cf8" strokeWidth={2.5} strokeLinejoin="round" />
  </svg>
)
