type DiffLineType = 'file-header' | 'hunk' | 'addition' | 'deletion' | 'context'

function classify(line: string): DiffLineType {
  if (line.startsWith('diff --git') || line.startsWith('---') || line.startsWith('+++')) return 'file-header'
  if (line.startsWith('@@')) return 'hunk'
  if (line.startsWith('+')) return 'addition'
  if (line.startsWith('-')) return 'deletion'
  return 'context'
}

export default function DiffViewer({ patch }: { patch: string }) {
  return (
    <div className="diff-viewer">
      {patch.split('\n').map((line, index) => (
        <div key={index} className={`diff-line ${classify(line)}`}>
          <code>{line}</code>
        </div>
      ))}
    </div>
  )
}
