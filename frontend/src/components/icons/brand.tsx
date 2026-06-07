/**
 * 品牌 / Logo 类图标
 *
 * `MoleculeLogo` 是 MBForge 的品牌标识 —— 与 `src/assets/logo.svg` 共用同一份设计。
 * SVG 内联到组件里（不引外部 asset），保证：
 *   - 离线 / 沙箱环境也能用
 *   - 不会撞 asset protocol CORS（之前修过 PDF 同类问题）
 *   - bundle 不增加外部 HTTP 请求
 *
 * 如果改 logo，**两处都要改**：
 *   1. `frontend/src/assets/logo.svg`         ← 源
 *   2. 本组件的 `<svg>` 块（直接复制 SVG 内容）
 *   3. 跑 `cargo tauri icon frontend/src/assets/logo.svg` 重新生成 OS icon
 */
import type { FC } from 'react'
import type { IconProps } from './types'

export const MoleculeLogo: FC<IconProps> = ({ size = 72 }) => (
  <svg width={size} height={size} viewBox="0 0 72 72" fill="none">
    <defs>
      <linearGradient id="mblogo-bg" x1="0" y1="0" x2="72" y2="72" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="#0f0f1e" />
        <stop offset="1" stopColor="#1a1a2e" />
      </linearGradient>
    </defs>

    <rect width="72" height="72" rx="16" fill="url(#mblogo-bg)" />

    {/* 大正六边形（center 36,36, R=12） —— 银灰半透明（在底层），居于 viewBox 正中央 */}
    <polygon
      points="36,24 46.4,30 46.4,42 36,48 25.6,42 25.6,30"
      stroke="#9ca3af" strokeWidth={2} strokeLinejoin="round" opacity={0.75}
    />

    {/* 小六边形 Top —— cyan */}
    <polygon
      points="36,16 42.9,20 42.9,28 36,32 29.1,28 29.1,20"
      stroke="#38bdf8" strokeWidth={2.5} strokeLinejoin="round"
    />
    {/* 小六边形 BR —— violet */}
    <polygon
      points="46.4,34 53.3,38 53.3,46 46.4,50 39.5,46 39.5,38"
      stroke="#a78bfa" strokeWidth={2.5} strokeLinejoin="round"
    />
    {/* 小六边形 BL —— indigo */}
    <polygon
      points="25.6,34 32.5,38 32.5,46 25.6,50 18.7,46 18.7,38"
      stroke="#818cf8" strokeWidth={2.5} strokeLinejoin="round"
    />
  </svg>
)
