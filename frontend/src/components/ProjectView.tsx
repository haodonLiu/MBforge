import { useState, useEffect } from 'react'
import { FolderIcon, FileTextIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon, ArrowLeftIcon, ChevronLeftIcon, ChevronRightIcon } from './icons'
import type { DocumentEntry } from '../types'
import { getProjectRoot } from '../hooks/useProjectRoot'
import ErrorBanner from './ErrorBanner'
import StatCard from './project/StatCard'

interface Molecule {
  name: string
  smiles: string
}

export default function ProjectView() {
  const [projectRoot, setProjectRoot] = useState(getProjectRoot())
  const [docs, setDocs] = useState<DocumentEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  // PDF 阅读状态
  const [selectedPdf, setSelectedPdf] = useState<DocumentEntry | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages] = useState(48)
  const [activeAnnotationTab, setActiveAnnotationTab] = useState<'highlights' | 'notes' | 'molecules'>('molecules')
  const [extractedMolecules] = useState<Molecule[]>([
    { name: '阿司匹林', smiles: 'CC(=O)Oc1ccccc1C(=O)O' },
    { name: '水杨酸', smiles: 'O=C(O)c1ccccc1O' },
    { name: '布洛芬', smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O' },
  ])

  const loadDocs = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    setError('')
    try {
      // 模拟数据
      setDocs([
        { doc_id: '1', path: '/docs/aspirin.pdf', title: '阿司匹林研究.pdf', doc_type: 'pdf', indexed: true },
        { doc_id: '2', path: '/docs/caffeine.pdf', title: '咖啡因分子结构.pdf', doc_type: 'pdf', indexed: true },
        { doc_id: '3', path: '/docs/ibuprofen.pdf', title: '布洛芬药代动力学.pdf', doc_type: 'pdf', indexed: false },
        { doc_id: '4', path: '/docs/notes.md', title: '研究笔记.md', doc_type: 'md', indexed: true },
      ])
    } catch (e) {
      console.error(e)
      setError('Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    setProjectRoot(getProjectRoot())
    loadDocs()
  }, [])

  const handleScan = async () => {
    loadDocs()
  }

  const handleOpenPdf = (doc: DocumentEntry) => {
    if (doc.doc_type === 'pdf') {
      setSelectedPdf(doc)
      setCurrentPage(1)
    }
  }

  const handleClosePdf = () => {
    setSelectedPdf(null)
  }

  const projectName = projectRoot ? projectRoot.split('/').pop() || projectRoot : '未选择项目'

  // PDF 视图
  if (selectedPdf) {
    return (
      <div style={{
        flex: 1,
        display: 'grid',
        gridTemplateColumns: '160px 1fr 280px',
        height: '100%',
        overflow: 'hidden',
      }}>
        {/* 左侧缩略图 */}
        <div style={{
          background: 'var(--bg-surface)',
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{
            padding: '12px 14px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '12px',
          }}>
            <span>页面</span>
            <span style={{ color: 'var(--text-muted)' }}>{currentPage}/{totalPages}</span>
          </div>
          <div style={{
            flex: 1,
            overflow: 'auto',
            padding: '12px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}>
            {[1, 2, 3, 4, 5, 6, 7].map(page => (
              <div
                key={page}
                onClick={() => setCurrentPage(page)}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '6px',
                  cursor: 'pointer',
                  opacity: page === currentPage ? 1 : 0.6,
                }}
              >
                <div style={{
                  width: '100%',
                  aspectRatio: '0.707',
                  background: 'white',
                  border: page === currentPage ? '2px solid var(--accent)' : '2px solid var(--border)',
                  borderRadius: '4px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '20px',
                  fontWeight: 600,
                  color: 'var(--text-muted)',
                  boxShadow: page === currentPage ? '0 2px 8px rgba(0,0,0,0.15)' : '0 2px 4px rgba(0,0,0,0.1)',
                }}>
                  {page}
                </div>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{page}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 主阅读区 */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          background: '#525659',
          overflow: 'hidden',
        }}>
          {/* 工具栏 */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            height: '48px',
            padding: '0 16px',
            background: 'var(--bg-surface)',
            borderBottom: '1px solid var(--border)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button
                onClick={handleClosePdf}
                style={{
                  width: '32px',
                  height: '32px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                }}
              >
                <ArrowLeftIcon size={18} />
              </button>
              <span style={{
                fontSize: '13px',
                fontWeight: 500,
                maxWidth: '200px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>{selectedPdf.title || selectedPdf.path}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                style={{
                  width: '28px',
                  height: '28px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: currentPage <= 1 ? 'default' : 'pointer',
                  color: currentPage <= 1 ? 'var(--text-muted)' : 'var(--text-secondary)',
                }}
              >
                <ChevronLeftIcon size={16} />
              </button>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{currentPage} / {totalPages}</span>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                style={{
                  width: '28px',
                  height: '28px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: currentPage >= totalPages ? 'default' : 'pointer',
                  color: currentPage >= totalPages ? 'var(--text-muted)' : 'var(--text-secondary)',
                }}
              >
                <ChevronRightIcon size={16} />
              </button>
            </div>
          </div>

          {/* PDF 内容区 */}
          <div style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontSize: '48px',
            fontWeight: 700,
          }}>
            {currentPage}
          </div>
        </div>

        {/* 右侧标注面板 */}
        <div style={{
          background: 'var(--bg-surface)',
          borderLeft: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--border)',
          }}>
            {(['molecules', 'highlights', 'notes'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveAnnotationTab(tab)}
                style={{
                  flex: 1,
                  padding: '12px 8px',
                  fontSize: '12px',
                  background: activeAnnotationTab === tab ? 'var(--accent-muted)' : 'transparent',
                  border: 'none',
                  borderBottom: activeAnnotationTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
                  color: activeAnnotationTab === tab ? 'var(--accent)' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                {tab === 'molecules' ? '分子' : tab === 'highlights' ? '标注' : '笔记'}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: '12px' }}>
            {activeAnnotationTab === 'molecules' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {extractedMolecules.map((mol, i) => (
                  <div key={i} style={{
                    padding: '10px 12px',
                    background: 'var(--bg-base)',
                    borderRadius: '8px',
                    border: '1px solid var(--border)',
                  }}>
                    <div style={{ fontSize: '13px', fontWeight: 500, marginBottom: '4px' }}>{mol.name}</div>
                    <div style={{
                      fontSize: '11px',
                      fontFamily: 'monospace',
                      color: 'var(--text-muted)',
                      maxWidth: '180px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {mol.smiles}
                    </div>
                  </div>
                ))}
                <button style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  width: '100%',
                  padding: '12px',
                  background: 'var(--bg-base)',
                  border: '1px dashed var(--border)',
                  borderRadius: '8px',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}>
                  <FlaskIcon size={14} /> 提取页面中的分子
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // 项目视图
  return (
    <div style={{
      flex: 1,
      padding: '32px',
      overflow: 'auto',
    }}>
      {error && <ErrorBanner message={error} onDismiss={() => setError('')} />}

      {/* 头部 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '32px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{
            width: '48px',
            height: '48px',
            borderRadius: '12px',
            background: 'var(--accent-muted)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent)',
          }}>
            <FolderIcon size={24} />
          </div>
          <div>
            <h1 style={{
              fontSize: 'var(--font-size-title)',
              fontWeight: 600,
            }}>{projectName}</h1>
            <p style={{
              fontSize: '13px',
              color: 'var(--text-muted)',
            }}>{projectRoot || '请先打开或创建一个项目'}</p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-secondary" onClick={handleScan} disabled={!projectRoot || isLoading} style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            fontSize: '13px',
          }}>
            <ExternalLinkIcon size={14} />
            {isLoading ? '扫描中...' : '扫描文件'}
          </button>
          <button className="btn btn-secondary" style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '8px 16px',
            fontSize: '13px',
          }}>
            <SettingsIcon size={14} />
            项目设置
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '16px',
        marginBottom: '32px',
      }}>
        <StatCard icon={<FileTextIcon size={18} />} value={String(docs.length)} label="文献" />
        <StatCard icon={<FlaskIcon size={18} />} value="128" label="分子" />
        <StatCard icon={<FileTextIcon size={18} />} value={String(docs.filter(d => d.indexed).length)} label="已索引" />
        <StatCard icon={<FolderIcon size={18} />} value={String(docs.length)} label="文件" />
      </div>

      {/* 文件列表 */}
      <h2 style={{
        fontSize: '16px',
        fontWeight: 600,
        marginBottom: '16px',
      }}>项目文件</h2>

      {docs.length === 0 ? (
        <div style={{
          padding: '40px',
          textAlign: 'center',
          color: 'var(--text-muted)',
          background: 'var(--bg-surface)',
          borderRadius: '12px',
          border: '1px solid var(--border)',
        }}>
          {projectRoot ? '暂无文件，点击"扫描文件"索引项目内容' : '请先打开或创建一个项目'}
        </div>
      ) : (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}>
          {docs.map(doc => (
            <div
              key={doc.doc_id}
              onClick={() => handleOpenPdf(doc)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '12px 16px',
                background: 'var(--bg-surface)',
                borderRadius: '8px',
                border: '1px solid var(--border)',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'var(--accent)'
                e.currentTarget.style.background = 'var(--accent-muted)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border)'
                e.currentTarget.style.background = 'var(--bg-surface)'
              }}
            >
              <FileTextIcon size={16} />
              <span style={{ flex: 1, fontSize: '14px' }}>{doc.title || doc.path}</span>
              <span style={{
                fontSize: '12px',
                color: 'var(--text-muted)',
                padding: '2px 8px',
                background: 'var(--bg-base)',
                borderRadius: '4px',
              }}>{doc.doc_type}</span>
              {doc.indexed ? (
                <span style={{
                  fontSize: '12px',
                  color: '#16a34a',
                  padding: '2px 8px',
                  background: 'rgba(22,163,74,0.1)',
                  borderRadius: '4px',
                }}>已索引</span>
              ) : (
                <span style={{
                  fontSize: '12px',
                  color: 'var(--text-muted)',
                  padding: '2px 8px',
                  background: 'var(--bg-base)',
                  borderRadius: '4px',
                }}>未索引</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
