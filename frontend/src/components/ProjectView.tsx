import { useState, useEffect } from 'react'
import { FolderIcon, FileTextIcon, FlaskIcon, ExternalLinkIcon, SettingsIcon, ArrowLeftIcon, ChevronLeftIcon, ChevronRightIcon } from './icons'
import type { DocumentEntry } from '../types'

function getProjectRoot(): string {
  return localStorage.getItem('mbforge_project_root') || ''
}

interface Molecule {
  name: string
  smiles: string
}

interface Highlight {
  text: string
  page: number
  color: string
}

interface Note {
  page: number
  content: string
}

export default function ProjectView() {
  const [projectRoot, setProjectRoot] = useState(getProjectRoot())
  const [docs, setDocs] = useState<DocumentEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  
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
  const [highlights] = useState<Highlight[]>([
    { text: '乙酰水杨酸（Acetylsalicylic acid）', page: 3, color: 'yellow' },
    { text: '抑制环氧化酶（COX-1 和 COX-2）', page: 5, color: 'green' },
    { text: '抗血小板：预防心血管事件', page: 7, color: 'blue' },
  ])
  const [notes] = useState<Note[]>([
    { page: 3, content: '阿司匹林是最早发现的 NSAID 类药物' },
    { page: 8, content: '注意阿司匹林与其他抗凝药物的相互作用' },
  ])

  const loadDocs = async () => {
    const root = getProjectRoot()
    if (!root) return
    setIsLoading(true)
    try {
      // 模拟数据
      setDocs([
        { doc_id: '1', path: '/docs/aspirin.pdf', title: '阿司匹林研究.pdf', doc_type: 'pdf', indexed: true },
        { doc_id: '2', path: '/docs/caffeine.pdf', title: '咖啡因分子结构.pdf', doc_type: 'pdf', indexed: true },
        { doc_id: '3', path: '/docs/ibuprofen.pdf', title: '布洛芬药代动力学.pdf', doc_type: 'pdf', indexed: false },
        { doc_id: '4', path: '/docs/notes.md', title: '研究笔记.md', doc_type: 'md', indexed: true },
      ])
    } catch (e) {
      // ignore
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
              }}>
                {selectedPdf.title}
              </span>
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
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
                <ChevronLeftIcon size={18} />
              </button>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '13px',
                color: 'var(--text-secondary)',
              }}>
                <input
                  type="number"
                  value={currentPage}
                  onChange={e => setCurrentPage(Math.max(1, Math.min(totalPages, parseInt(e.target.value) || 1)))}
                  style={{
                    width: '48px',
                    padding: '4px 8px',
                    textAlign: 'center',
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    borderRadius: '6px',
                    fontSize: '13px',
                    color: 'var(--text-primary)',
                  }}
                />
                <span>/ {totalPages}</span>
              </div>
              <button
                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
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
                <ChevronRightIcon size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button style={{
                width: '32px',
                height: '32px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--accent)',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                color: 'white',
              }}>
                <FlaskIcon size={16} />
              </button>
              <button style={{
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
              }}>
                🔍
              </button>
            </div>
          </div>

          {/* 提取分子快捷栏 */}
          <div style={{
            background: 'var(--bg-surface)',
            borderBottom: '1px solid var(--border)',
            padding: '12px 16px',
          }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '10px',
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13px',
                fontWeight: 500,
              }}>
                <FlaskIcon size={16} style={{ color: 'var(--accent)' }} />
                检测到 {extractedMolecules.length} 个分子
              </div>
              <button style={{
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: 500,
                background: 'var(--accent)',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
              }}>
                提取全部 →
              </button>
            </div>
            <div style={{
              display: 'flex',
              gap: '10px',
              overflowX: 'auto',
            }}>
              {extractedMolecules.map((mol, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                    padding: '10px 14px',
                    background: 'var(--bg-base)',
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    flexShrink: 0,
                  }}
                >
                  <span style={{ fontSize: '13px', fontWeight: 500 }}>{mol.name}</span>
                  <span style={{
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    color: 'var(--text-muted)',
                    maxWidth: '180px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {mol.smiles}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* PDF 内容区 */}
          <div style={{
            flex: 1,
            overflow: 'auto',
            display: 'flex',
            justifyContent: 'center',
            padding: '24px',
          }}>
            <div style={{
              width: '100%',
              maxWidth: '800px',
              background: 'white',
              borderRadius: '4px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
              padding: '48px 56px',
              minHeight: '100%',
              color: '#333',
              fontSize: '14px',
              lineHeight: '1.8',
            }}>
              <div style={{
                marginBottom: '32px',
                paddingBottom: '16px',
                borderBottom: '2px solid #eee',
              }}>
                <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>
                  {selectedPdf.title.replace('.pdf', '')}
                </h1>
                <p style={{ fontSize: '12px', color: '#888' }}>第 {currentPage} 页 / 共 {totalPages} 页</p>
              </div>
              
              {currentPage === 3 && (
                <>
                  <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '28px 0 16px' }}>1. 引言</h2>
                  <p style={{ marginBottom: '16px' }}>
                    阿司匹林（Aspirin），化学名称为乙酰水杨酸（Acetylsalicylic acid，ASA），是一种广泛应用于临床的非甾体抗炎药（NSAID）。自1899年上市以来，阿司匹林已成为世界上使用最广泛的药物之一。
                  </p>
                  
                  <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '28px 0 16px' }}>2. 化学结构</h2>
                  <p style={{ marginBottom: '16px' }}>
                    阿司匹林的分子式为 C₉H₈O₄，分子量为 180.16 g/mol。其化学结构包含一个苯环、一个羧基（-COOH）和一个乙酰氧基（-OCOCH₃）。
                  </p>
                  
                  <div style={{
                    display: 'flex',
                    gap: '16px',
                    padding: '16px',
                    background: '#f8f9fa',
                    border: '1px solid #e9ecef',
                    borderLeft: '4px solid var(--accent)',
                    borderRadius: '8px',
                    margin: '24px 0',
                  }}>
                    <div style={{
                      width: '48px',
                      height: '48px',
                      background: 'var(--accent)',
                      borderRadius: '10px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'white',
                      fontSize: '24px',
                    }}>
                      🧪
                    </div>
                    <div>
                      <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>分子信息</div>
                      <div style={{ fontSize: '12px' }}>
                        <div><span style={{ color: '#666' }}>SMILES:</span> <code style={{ background: '#eee', padding: '2px 6px', borderRadius: '4px' }}>CC(=O)Oc1ccccc1C(=O)O</code></div>
                        <div><span style={{ color: '#666' }}>分子量:</span> <code>180.16 g/mol</code></div>
                      </div>
                    </div>
                  </div>
                  
                  <h2 style={{ fontSize: '18px', fontWeight: 600, margin: '28px 0 16px' }}>3. 药理学特性</h2>
                  <p style={{ marginBottom: '16px' }}>
                    阿司匹林通过抑制环氧化酶（COX-1 和 COX-2）来发挥其抗炎、镇痛和解热作用。这种抑制是不可逆的。
                  </p>
                </>
              )}
              
              {currentPage !== 3 && (
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '80px',
                  color: '#999',
                }}>
                  <div style={{ fontSize: '120px', opacity: 0.2 }}>{currentPage}</div>
                  <p style={{ marginTop: '16px' }}>第 {currentPage} 页内容</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 右侧注释面板 */}
        <div style={{
          background: 'var(--bg-surface)',
          borderLeft: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
        }}>
          {/* Tab 切换 */}
          <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--border)',
          }}>
            {(['highlights', 'notes', 'molecules'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveAnnotationTab(tab)}
                style={{
                  flex: 1,
                  padding: '12px',
                  fontSize: '12px',
                  fontWeight: 500,
                  background: 'transparent',
                  border: 'none',
                  borderBottom: activeAnnotationTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
                  color: activeAnnotationTab === tab ? 'var(--accent)' : 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                {tab === 'highlights' ? '高亮' : tab === 'notes' ? '笔记' : '分子'}
              </button>
            ))}
          </div>

          {/* 内容 */}
          <div style={{ flex: 1, overflow: 'auto', padding: '12px' }}>
            {activeAnnotationTab === 'highlights' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {highlights.map((h, i) => (
                  <div key={i} style={{
                    display: 'flex',
                    gap: '10px',
                    padding: '12px',
                    background: 'var(--bg-base)',
                    borderRadius: '8px',
                  }}>
                    <div style={{
                      width: '12px',
                      height: '12px',
                      borderRadius: '3px',
                      background: h.color === 'yellow' ? '#ffeb3b' : h.color === 'green' ? '#4caf50' : '#2196f3',
                      marginTop: '4px',
                      flexShrink: 0,
                    }} />
                    <div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                        "{h.text}"
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '6px' }}>
                        第 {h.page} 页 · <a href="#" style={{ color: 'var(--accent)' }}>跳转</a>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeAnnotationTab === 'notes' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {notes.map((n, i) => (
                  <div key={i} style={{
                    padding: '12px',
                    background: 'var(--bg-base)',
                    borderRadius: '8px',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>第 {n.page} 页</span>
                      <button style={{ fontSize: '12px', background: 'transparent', border: 'none', cursor: 'pointer' }}>✏️</button>
                    </div>
                    <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                      {n.content}
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
                  + 添加笔记
                </button>
              </div>
            )}

            {activeAnnotationTab === 'molecules' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {extractedMolecules.map((mol, i) => (
                  <div key={i} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '12px',
                    background: 'var(--bg-base)',
                    borderRadius: '8px',
                    cursor: 'pointer',
                  }}>
                    <div style={{
                      width: '40px',
                      height: '40px',
                      background: 'var(--bg-surface)',
                      borderRadius: '8px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      <FlaskIcon size={20} style={{ color: 'var(--text-muted)' }} />
                    </div>
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 500 }}>{mol.name}</div>
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

function StatCard({ icon, value, label }: { icon: React.ReactNode; value: string; label: string }) {
  return (
    <div style={{
      padding: '20px',
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: '12px',
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
    }}>
      <div style={{ color: 'var(--text-muted)' }}>{icon}</div>
      <div>
        <div style={{
          fontSize: '20px',
          fontWeight: 700,
        }}>{value}</div>
        <div style={{
          fontSize: '12px',
          color: 'var(--text-muted)',
        }}>{label}</div>
      </div>
    </div>
  )
}
