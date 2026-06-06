import { useState } from 'react'
import LowConfidenceBanner from './molecule/LowConfidenceBanner'
import { useConfidenceThreshold } from '../hooks/useConfidenceThreshold'
export interface Molecule {
  id: string
  smiles: string
  name: string
  confidence: number
  imagePath?: string
  status: 'pending' | 'accepted' | 'rejected' | 'edited'
}

interface MoleculeReviewPanelProps {
  molecules: Molecule[]
  onAccept: (id: string) => void
  onReject: (id: string) => void
  onEdit: (id: string, newSmiles: string) => void
  onApproveAll: () => void
  onRejectAll: () => void
}

export default function MoleculeReviewPanel({
  molecules,
  onAccept,
  onReject,
  onEdit,
  onApproveAll,
  onRejectAll,
}: MoleculeReviewPanelProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editSmiles, setEditSmiles] = useState('')
  // O-01/O-02 共用阈值 — 与 CorrectionPanel.handleFinish 同一份 localStorage
  const [threshold] = useConfidenceThreshold()

  const handleEdit = (molecule: Molecule) => {
    setEditingId(molecule.id)
    setEditSmiles(molecule.smiles)
  }

  const handleSaveEdit = () => {
    if (editingId) {
      onEdit(editingId, editSmiles)
      setEditingId(null)
    }
  }

  const pendingCount = molecules.filter((m) => m.status === 'pending').length

  return (
    <div className="molecule-review-panel">
      <div className="panel-header">
        <h2>Molecule Detection Results</h2>
        <div className="actions">
          <button onClick={onApproveAll} disabled={pendingCount === 0}>
            Approve All ({pendingCount})
          </button>
          <button onClick={onRejectAll} disabled={pendingCount === 0}>
            Reject All
          </button>
        </div>
      </div>

      {/* O-02：项目级低置信度全局提醒 — 复用 O-01 阈值 */}
      <LowConfidenceBanner molecules={molecules} />

      <div className="molecule-list">
        {molecules.map((molecule) => (
          <div
            key={molecule.id}
            className={`molecule-card ${molecule.status}`}
          >
            <div className="molecule-image">
              {molecule.imagePath ? (
                <img
                  src={molecule.imagePath}
                  alt={molecule.name || molecule.smiles}
                />
              ) : (
                <div className="placeholder">No image</div>
              )}
            </div>

            <div className="molecule-info">
              <div className="smiles">{molecule.smiles}</div>
              {molecule.name && <div className="name">{molecule.name}</div>}
              {/* O-02：复用 O-01 阈值（默认 0.5），不再硬编码 0.6 */}
              <div
                className={`confidence ${molecule.confidence < threshold ? 'low' : ''}`}
              >
                Confidence: {(molecule.confidence * 100).toFixed(1)}%
              </div>
            </div>

            <div className="molecule-actions">
              {editingId === molecule.id ? (
                <div className="edit-form">
                  <input
                    type="text"
                    value={editSmiles}
                    onChange={(e) => setEditSmiles(e.target.value)}
                    placeholder="Enter SMILES"
                  />
                  <button onClick={handleSaveEdit}>Save</button>
                  <button onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              ) : (
                <>
                  <button
                    onClick={() => onAccept(molecule.id)}
                    disabled={molecule.status !== 'pending'}
                  >
                    Accept
                  </button>
                  <button
                    onClick={() => onReject(molecule.id)}
                    disabled={molecule.status !== 'pending'}
                  >
                    Reject
                  </button>
                  <button onClick={() => handleEdit(molecule)}>Edit</button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
