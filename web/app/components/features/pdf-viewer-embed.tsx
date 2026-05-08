'use client'

import { PDFViewer } from '@embedpdf/react-pdf-viewer'

type Props = {
  src: string
  className?: string
}

/**
 * EmbedPDF drop-in viewer — loads PDF via URL (e.g. same-origin API proxy with inline disposition).
 */
export function PdfViewerEmbed({ src, className }: Props) {
  return (
    <div className={className ?? 'h-full w-full min-h-[480px]'}>
      <PDFViewer
        config={{
          src,
          theme: { preference: 'light' },
        }}
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  )
}
