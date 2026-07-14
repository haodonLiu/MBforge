export function cleanMoleculePlaceholders(markdown: string): string {
  return markdown
    .replace(/^\s*<!--\s*Molecule\s+([^>]+?)\s*-->\s*$/gim, '')
    .replace(
      /```[^\n]*\nMoleCode not available for ([^\n]+)\n```/gi,
      '> Structure not generated for $1.',
    )
}
