import { useRef, useState } from 'react'

const s = {
  zone: {
    borderWidth: 2, borderStyle: 'dashed', borderColor: '#4a5568',
    borderRadius: 8, padding: 24,
    textAlign: 'center', cursor: 'pointer', transition: 'all 0.2s',
    background: '#1a1f2e',
  },
  zoneActive: { borderColor: '#63b3ed', background: '#1e2a3a' },
  label: { color: '#a0aec0', fontSize: 14, marginTop: 8 },
  files: { marginTop: 8, fontSize: 13, color: '#68d391' },
}

export default function DropZone({ label, accept = '.pdf', multiple = false, onFiles }) {
  const [dragging, setDragging] = useState(false)
  const [fileNames, setFileNames] = useState([])
  const inputRef = useRef()

  const handle = (files) => {
    const arr = Array.from(files)
    setFileNames(arr.map(f => f.name))
    onFiles(multiple ? arr : arr[0])
  }

  return (
    <div
      style={{ ...s.zone, ...(dragging ? s.zoneActive : {}) }}
      onClick={() => inputRef.current.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); handle(e.dataTransfer.files) }}
    >
      <div style={{ fontSize: 28 }}>📄</div>
      <div style={s.label}>{label || (multiple ? 'PDF 여러 개 드래그 또는 클릭' : 'PDF 드래그 또는 클릭')}</div>
      {fileNames.length > 0 && (
        <div style={s.files}>
          {fileNames.map((n, i) => <div key={i}>✓ {n}</div>)}
        </div>
      )}
      <input
        ref={inputRef} type="file" accept={accept}
        multiple={multiple} style={{ display: 'none' }}
        onChange={e => handle(e.target.files)}
      />
    </div>
  )
}
