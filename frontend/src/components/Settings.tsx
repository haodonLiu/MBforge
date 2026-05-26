import { useState } from 'react'
import { SettingsIcon } from './icons'

type Section = 'general' | 'ai' | 'embedding' | 'reranker' | 'appearance' | 'server' | 'about'

const SECTIONS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: 'general', label: '通用', icon: <SettingsIcon size={18} /> },
  { id: 'ai', label: 'AI 模型', icon: <SettingsIcon size={18} /> },
  { id: 'embedding', label: 'Embedding', icon: <SettingsIcon size={18} /> },
  { id: 'reranker', label: 'Reranker', icon: <SettingsIcon size={18} /> },
  { id: 'appearance', label: '外观', icon: <SettingsIcon size={18} /> },
  { id: 'server', label: '模型服务', icon: <SettingsIcon size={18} /> },
  { id: 'about', label: '关于', icon: <SettingsIcon size={18} /> },
]

export default function Settings() {
  const [activeSection, setActiveSection] = useState<Section>('general')
  const [fontSize, setFontSize] = useState('medium')

  const renderSection = () => {
    switch (activeSection) {
      case 'general':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">项目</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">自动打开最近项目</div>
                  <div className="setting-desc">启动时自动加载上次使用的项目</div>
                </div>
                <label className="toggle">
                  <input type="checkbox" defaultChecked />
                  <span className="toggle-slider"></span>
                </label>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">自动处理导入文件</div>
                  <div className="setting-desc">将导入的文件自动添加到处理队列</div>
                </div>
                <label className="toggle">
                  <input type="checkbox" />
                  <span className="toggle-slider"></span>
                </label>
              </div>
            </div>
            <div className="settings-group">
              <h3 className="settings-group-title">文件</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">默认 PDF 阅读器</div>
                  <div className="setting-desc">选择用于查看 PDF 的应用</div>
                </div>
                <select className="setting-select">
                  <option>内置查看器</option>
                  <option>系统默认</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">索引并发数</div>
                  <div className="setting-desc">同时处理的文件数量</div>
                </div>
                <select className="setting-select">
                  <option>2</option>
                  <option selected>4</option>
                  <option>8</option>
                </select>
              </div>
            </div>
          </div>
        )

      case 'ai':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">语言模型</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Provider</div>
                </div>
                <select className="setting-select">
                  <option selected>OpenAI</option>
                  <option>Anthropic</option>
                  <option>本地模型</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">模型</div>
                </div>
                <select className="setting-select">
                  <option selected>gpt-4o</option>
                  <option>gpt-4-turbo</option>
                  <option>gpt-3.5-turbo</option>
                </select>
              </div>
              <div className="setting-item vertical">
                <div className="setting-info">
                  <div className="setting-label">API Key</div>
                  <div className="setting-desc">你的 API 密钥</div>
                </div>
                <div className="setting-input-wrapper">
                  <input type="password" className="setting-input" placeholder="sk-..." defaultValue="sk-xxxx...xxxx" />
                </div>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Temperature</div>
                  <div className="setting-desc">控制输出的随机性 (0-2)</div>
                </div>
                <div className="range-wrapper">
                  <input type="range" className="setting-range" min="0" max="2" step="0.1" defaultValue="0.7" />
                  <span className="range-value">0.7</span>
                </div>
              </div>
            </div>
          </div>
        )

      case 'embedding':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">Embedding 模型</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Provider</div>
                </div>
                <select className="setting-select">
                  <option selected>OpenAI</option>
                  <option>本地模型</option>
                  <option>HuggingFace</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">模型</div>
                </div>
                <select className="setting-select">
                  <option selected>text-embedding-3-small</option>
                  <option>text-embedding-3-large</option>
                  <option>text-embedding-ada-002</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">向量维度</div>
                </div>
                <select className="setting-select">
                  <option selected>1536</option>
                  <option>3072</option>
                </select>
              </div>
            </div>
          </div>
        )

      case 'reranker':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">Reranker 模型</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">启用 Reranker</div>
                  <div className="setting-desc">对搜索结果进行重排序以提高相关性</div>
                </div>
                <label className="toggle">
                  <input type="checkbox" defaultChecked />
                  <span className="toggle-slider"></span>
                </label>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">模型</div>
                </div>
                <select className="setting-select">
                  <option selected>cohere rerank</option>
                  <option>Jina Reranker</option>
                </select>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">Top N</div>
                  <div className="setting-desc">返回的重排序结果数量</div>
                </div>
                <input type="number" className="setting-number" defaultValue={10} min={1} max={100} />
              </div>
            </div>
          </div>
        )

      case 'appearance':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">主题</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">外观模式</div>
                </div>
                <div className="theme-selector">
                  <div className="theme-option active">
                    <div className="theme-preview light"></div>
                    <span>浅色</span>
                  </div>
                  <div className="theme-option">
                    <div className="theme-preview dark"></div>
                    <span>深色</span>
                  </div>
                  <div className="theme-option">
                    <div className="theme-preview system"></div>
                    <span>跟随系统</span>
                  </div>
                </div>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">字体大小</div>
                </div>
                <select className="setting-select" value={fontSize} onChange={e => setFontSize(e.target.value)}>
                  <option value="small">小 (13px)</option>
                  <option value="medium">中 (14px)</option>
                  <option value="large">大 (15px)</option>
                </select>
              </div>
            </div>
          </div>
        )

      case 'server':
        return (
          <div className="settings-section">
            <div className="settings-group">
              <h3 className="settings-group-title">本地模型服务</h3>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">自动启动服务</div>
                  <div className="setting-desc">应用启动时自动运行模型服务</div>
                </div>
                <label className="toggle">
                  <input type="checkbox" defaultChecked />
                  <span className="toggle-slider"></span>
                </label>
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">服务地址</div>
                </div>
                <input type="text" className="setting-input-text" defaultValue="localhost" />
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">服务端口</div>
                </div>
                <input type="number" className="setting-number" defaultValue={8000} min={1} max={65535} />
              </div>
              <div className="setting-item">
                <div className="setting-info">
                  <div className="setting-label">启动超时</div>
                  <div className="setting-desc">服务启动的最大等待时间（秒）</div>
                </div>
                <input type="number" className="setting-number" defaultValue={30} min={5} max={300} />
              </div>
            </div>
          </div>
        )

      case 'about':
        return (
          <div className="settings-section about-section">
            <div className="about-logo">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={36} height={36}>
                <path d="M10 2v7.31" />
                <path d="M14 9.3V1.99" />
                <path d="M8.5 2h7" />
                <path d="M14 9.3a6.5 6.5 0 1 1-4 0" />
                <path d="M5.58 16.5h12.85" />
              </svg>
            </div>
            <h2 className="about-title">MBForge</h2>
            <p className="about-version">版本 1.0.0</p>
            <p className="about-desc">Molecular Knowledge Base - 分子知识库</p>
            <div className="about-links">
              <a href="#">📖 文档</a>
              <a href="#">💻 GitHub</a>
              <a href="#">🐛 问题反馈</a>
            </div>
          </div>
        )
    }
  }

  return (
    <div className="settings-layout">
      {/* 左侧导航 */}
      <div className="settings-nav">
        <div className="settings-nav-title">设置</div>
        {SECTIONS.map(section => (
          <button
            key={section.id}
            className={`settings-nav-item ${activeSection === section.id ? 'active' : ''}`}
            onClick={() => setActiveSection(section.id)}
          >
            {section.icon}
            <span>{section.label}</span>
          </button>
        ))}
      </div>

      {/* 右侧内容 */}
      <div className="settings-content">
        <div className="settings-header">
          <h3 className="settings-section-title">
            {SECTIONS.find(s => s.id === activeSection)?.label}
          </h3>
        </div>
        {renderSection()}
        <div className="settings-footer">
          <button className="btn btn-secondary">取消</button>
          <button className="btn btn-primary">保存设置</button>
        </div>
      </div>
    </div>
  )
}
