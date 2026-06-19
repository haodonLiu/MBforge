import { useAppContext } from '../../context/AppContext'
import { LayoutIcon } from '../icons'
import type { Tab } from '../../context/AppContext'

/**
 * 标签栏组件。
 *
 * 结构：
 * - 固定的 Project tab（不可关闭，始终在最左）
 * - 分隔线
 * - 动态文件标签（每个对应一个打开的 PDF/Markdown 文件）
 *
 * 仅在 openTabs 有内容时渲染。
 */
export default function TabBar() {
  const { openTabs, activeTabId, closeTab, setActiveTabId } = useAppContext()

  if (openTabs.length === 0) return null

  return (
    <div className="tab-bar">
      {/* Project tab — 不可关闭 */}
      <button
        className={`tab-item${activeTabId === null ? ' active' : ''}`}
        onClick={() => setActiveTabId(null)}
        title="Project"
      >
        <LayoutIcon size={14} />
        <span>Project</span>
      </button>

      {/* 分隔线 */}
      <div className="tab-separator" />

      {/* 动态文件标签 */}
      {openTabs.map((tab: Tab) => (
        <button
          key={tab.id}
          className={`tab-item${activeTabId === tab.id ? ' active' : ''}`}
          onClick={() => setActiveTabId(tab.id)}
          title={tab.title}
        >
          <span className="tab-label">{tab.title}</span>
          <span
            className="tab-close"
            onClick={(e) => {
              e.stopPropagation()
              closeTab(tab.id)
            }}
            title="关闭"
          >
            ✕
          </span>
        </button>
      ))}
    </div>
  )
}
