import sys, os
sys.path.insert(0, 'src')

from mbforge.core.document import DocumentProcessor, ExtractedContent
from mbforge.core.document_tree import extract_headings, DocumentTreeIndex, SectionChunk

pdf_path = r'C:\Users\10954\Desktop\X2\US20260027089A1.PDF'
print(f'Processing: {pdf_path}')
print(f'File exists: {os.path.exists(pdf_path)}')

content = DocumentProcessor.process(pdf_path)
print(f'\nPages: {content.metadata.get("pages")}')
print(f'Text length: {len(content.text)} chars')
print(f'Headings: {len(content.headings)}')
print(f'Sections: {len(content.sections)}')
print(f'Chunks: {len(content.chunks)}')

print('\n=== FIRST 10 HEADINGS ===')
for h in content.headings[:10]:
    print(f'  L{h["level"]} line{h["line_num"]}: {h["title"][:80]}')

print('\n=== FIRST 10 SECTIONS ===')
for s in content.sections[:10]:
    preview = s.text[:100].replace('\n', ' ')
    print(f'  [{s.path}] p.{s.page_start}-{s.page_end} ({len(s.text)} chars): {preview}...')

print('\n=== LONGEST SECTIONS ===')
sorted_sections = sorted(content.sections, key=lambda x: len(x.text), reverse=True)[:5]
for s in sorted_sections:
    print(f'  [{s.path}] p.{s.page_start}-{s.page_end}: {len(s.text)} chars')
