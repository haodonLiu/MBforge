# MBForge UI Redesign Specification

## Overview

Redesign the MBForge PyQt6 desktop application with a cohesive "Precision Scientific" aesthetic — professional and trustworthy, avoiding the cluttered look of traditional scientific software. Support both light and dark themes with system-following + manual override.

**Status:** Draft

---

## Design Direction

**Aesthetic:** 「精准科学感」+「现代极简」

---

## Color System

### Light Mode Palette

| Token | Hex | Usage |
|---|---|---|
| `brand_primary` | `#0F4C81` | Brand primary — navigation, active states, accents |
| `brand_primary_light` | `#3D5A80` | Secondary brand, hover states |
| `brand_primary_deep` | `#0A3A62` | Dark variant — top bar, active titles |
| `accent_amber` | `#F4A261` | Active data, warnings, attention |
| `accent_coral` | `#E76F51` | Danger operations, PDF files |
| `success` | `#2A9D8F` | Success states, validation, verified |
| `bg_base` | `#F7F9FC` | Window background (cold gray-white) |
| `bg_card` | `#FFFFFF` | Card / panel background |
| `bg_hover` | `#EDF2F7` | Row/item hover state |
| `bg_zebra` | `#F7F9FC` | Table zebra stripe (even rows) |
| `text_primary` | `#1D3557` | Main text — slightly softer than black |
| `text_secondary` | `#8D99AE` | Labels, placeholders, disabled |
| `border` | `#E9ecef` | Dividers, input borders |
| `border_focus` | `#0F4C81` | Focus ring for inputs |

### Dark Mode Palette

| Token | Hex | Usage |
|---|---|---|
| `brand_primary` | `#4A90D9` | Brighter blue for dark backgrounds |
| `brand_primary_light` | `#6BA3D6` | Hover states |
| `brand_primary_deep` | `#1D3557` | Deep blue for contrast areas |
| `accent_amber` | `#F4A261` | Same as light |
| `accent_coral` | `#E76F51` | Same as light |
| `success` | `#2A9D8F` | Same as light |
| `bg_base` | `#0F1419` | Window background |
| `bg_card` | `#1A1F26` | Card / panel background |
| `bg_hover` | `#2A3441` | Row/item hover state |
| `bg_zebra` | `#1A1F26` | Table zebra stripe |
| `text_primary` | `#E8EDF2` | Main text |
| `text_secondary` | `#6B7A8C` | Labels, placeholders |
| `border` | `#2A3441` | Dividers |
| `border_focus` | `#4A90D9` | Focus ring |

---

## Layout Structure

```
┌──────────────────────────────────────────────────────┐
│  Top bar (brand_primary_deep, 48px)                │
│  [Menu items]              [Service Dots ● ● ● ●]  │
├─────────┬──────────────────────────────┬────────────┤
│ Left    │ Center                       │ Right      │
│ 240px   │ Flexible                     │ 280px      │
│         │ ┌────────────────────────┐  │            │
│ [Proj]  │ │ WelcomeWidget / Tabs   │  │ KB Search  │
│ [Home]  │ │                        │  │ Chat       │
│ [Tree]  │ └────────────────────────┘  │            │
│ [Btns]  │                              │            │
├─────────┴──────────────────────────────┴────────────┤
│  Status bar (28px) [CPU] [Memory]     [Progress]   │
└──────────────────────────────────────────────────────┘
```

**Spacing rules:**
- Large gaps between modules: 16-24px (use whitespace, not dividers)
- Small gaps within a module: 8-12px
- Content edges: minimum 12px from window edge

---

## Component Style Guide

### Tab Bar (QTabWidget)
- Active tab: white/transparent bg + 2px bottom border in `brand_primary`
- Inactive tab: `text_secondary` color, transparent bg
- Hover: inactive bg → `bg_hover`
- Close button: hidden by default, fade in on hover (200ms)
- No bold fonts; active tab uses medium weight

### Buttons
- **Primary:** `brand_primary` bg, white text, 6px radius, no border
  - Hover: brightness +10%
  - Active: scale to 95%
- **Secondary:** transparent bg, `brand_primary` text, 1px `brand_primary` border
  - Hover: `brand_primary` 10% fill
- **Toolbar:** icon-only, 24×24px, hover shows circular `bg_hover` bg
- **Danger:** `accent_coral` text/border, hover fills `accent_coral` bg

### Input & Search
- **Normal:** only bottom 1px border in `border` color (flat)
- **Focus:** bottom border → `brand_primary` + 2px glow shadow below
- **Search box:** pill shape (20px radius), magnifying glass icon left, placeholder "搜索..."

### File Tree (Left Panel)
- Folder: outline icon; PDF: `accent_coral`; database: `success`
- Expand/collapse: `>` chevron with 90° rotation animation
- Selected item: `bg_hover` + 3px left border in `brand_primary`

### Data Tables
- Header: 12px size, medium weight, `text_secondary`, 1px bottom border
- Row height: 40-44px
- Zebra: even rows → `bg_zebra`
- Row hover: `bg_hover` + 3px left border slides in (150ms)
- Selected row: `brand_primary` 10% opacity bg + left border

### Empty States
- Centered illustration (large outline molecule, 20% opacity)
- Title in `text_primary`, subtitle in `text_secondary`
- One primary action button + optional secondary button

### Status Indicator (Top Right)
- 4 colored dots: green (`#40c057`) = online, gray (`#868e96`) = offline
- Hover tooltip shows full status text per service

### Service Status Dashboard (Removed from Right Panel)
- Moved to: resource monitor → status bar (permanent widgets)
- Service dots → top bar right corner

---

## Motion & Micro-interactions

| Trigger | Effect | Duration |
|---|---|---|
| Tab switch | Active indicator bar slides (not jumps) | 250ms ease-out |
| Row hover | Background fade in + left border slides in | 150ms |
| Button click | Scale to 95% + brightness shift | 100ms |
| Panel expand | Width animation + content fade | 300ms |
| Empty → Data | Fade in + translateY(10px→0) | 400ms |
| Loading | Skeleton shimmer (not spinner) | loop |

---

## Typography

- **Chinese:** System default (PingFang SC / Microsoft YaHei)
- **Weights:** 400 (body), 500 (labels/headers), 700 (titles)
- **Scale:**
  - Window title: 16px medium
  - Tab/table header: 13px medium
  - Body/table: 13px regular
  - Caption/hint: 11px regular, `text_secondary`

---

## Theme Switching Architecture

### Two-Tier System
1. **Global palette via `QStyleHints`** — Read system dark/light preference on startup via `QStyleHints.colorScheme()`
2. **Manual override in settings** — User can force light/dark in `SettingsDialog`, stored in `ProjectSettings`
3. **Signal-based propagation** — `ThemeManager` holds current palette, emits `theme_changed` signal; all widgets subscribe and call `setStyleSheet()` or update palette on change

### Implementation
- `ThemeManager` becomes the single source of truth for current palette dict
- All hardcoded color hex values in files replaced with `ThemeManager.get_color("token_name")`
- PyQt6's `QPalette` used where native Qt widgets need palette (not all widgets support QSS for everything)
- `SettingsDialog` adds a "主题" tab: [跟随系统 / 浅色 / 深色] radio buttons

### Files to Change
1. `theme.py` — Replace color constants with palette dict + light/dark variants; add `ThemeManager.theme_changed` signal
2. `components.py` — Update `StatusBadge`, `InfoRow`, `EmptyStateWidget`, `SectionHeader` to use theme
3. `main_window.py` — Home button styling, service indicator dots, status bar
4. `chat_widget.py` — Message bubbles, input area
5. `welcome_widget.py` — Card backgrounds, recent project rows
6. `kb_panel.py` — Fragment list, detail panel
7. `pdf_library.py` — PDF list, detail preview
8. `mol_panel.py` — Table, structure preview
9. `pdf_viewer.py` — Toolbar, page navigation
10. `file_tree.py` — Item styles
11. `todo_panel.py` — List items, progress
12. `dialogs.py` — Dialog styling

---

## Icon Style

- Style: outline icons, 2px stroke, rounded caps
- Sizes: toolbar 24px, list 16px, button 20px
- Color: `text_secondary` default, `brand_primary` on hover/active, 30% opacity when disabled
- Chemistry icons: geometric abstraction (hexagon = benzene ring, ball-and-stick simplified)

---

## Implementation Phases

### Phase 1: Foundation (theme.py + ThemeManager)
- Define light/dark palette dicts
- Add `ThemeManager.get_color(key)` and `theme_changed` signal
- Add `colorSchemeChanged` listener for system follow
- Add `is_dark_mode()` helper
- Update all factory functions in `theme.py` to use palette

### Phase 2: Core Components (components.py)
- Update StatusBadge, InfoRow, EmptyStateWidget, SectionHeader to use theme

### Phase 3: Main Window + Panels
- Apply new styles to main_window, welcome_widget, chat_widget, kb_panel, pdf_library, mol_panel, pdf_viewer, file_tree, todo_panel, dialogs
- Fix hardcoded color values throughout

### Phase 4: Settings Integration
- Add theme picker in SettingsDialog
- Persist override in ProjectSettings
- Wire up ThemeManager override

---

## References

- Figma: tab interactions, empty states
- VS Code: sidebar ↔ content area hierarchy
- Notion: whitespace philosophy, minimal buttons
- ChemDraw: scientific feel (without dated gradients)
- Linear: modern SaaS motion quality, dark/light balance
