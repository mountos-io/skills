// Build a single self-contained Markdown file per skill, for agents that cannot
// follow relative links or read a directory: paste it, or fetch it by raw URL.
//
// `make bundle`       writes <skill>/<skill>.bundle.md
// `make bundle-check` fails if a committed bundle is stale (run by `make check`)
import { readFileSync, readdirSync, existsSync, writeFileSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const checkOnly = process.argv.includes('--check')

const skills = readdirSync(root, { withFileTypes: true })
  .filter((d) => d.isDirectory() && !d.name.startsWith('.') &&
    !['node_modules', 'scripts'].includes(d.name) &&
    existsSync(join(root, d.name, 'SKILL.md')))
  .map((d) => d.name)

let stale = 0

for (const skill of skills) {
  const dir = join(root, skill)
  const skillMd = readFileSync(join(dir, 'SKILL.md'), 'utf8')

  // Strip the YAML frontmatter; it is host-specific metadata, not content.
  const body = skillMd.replace(/^---\n[\s\S]*?\n---\n/, '')
  const meta = skillMd.match(/^---\n([\s\S]*?)\n---\n/)?.[1] ?? ''
  const version = meta.match(/^version:\s*(\S+)/m)?.[1] ?? 'unknown'

  const refs = existsSync(join(dir, 'references'))
    ? readdirSync(join(dir, 'references')).filter((f) => f.endsWith('.md')).sort()
    : []

  const parts = [
    `# mountOS ${skill} skill (single-file bundle, version ${version})`,
    '',
    'This file is the entire skill in one document: the entry point followed by every',
    'reference it links to. It exists for agents that cannot follow relative links or read',
    'a directory. The links below point at sections in this same file.',
    '',
    'Source and updates: https://github.com/mountos-io/skills',
    '',
    '---',
    '',
    // Rewrite relative reference links to in-document anchors.
    body.replace(/\(references\/([a-z-]+)\.md\)/g, '(#reference-$1)'),
  ]

  for (const r of refs) {
    const name = r.replace(/\.md$/, '')
    const text = readFileSync(join(dir, 'references', r), 'utf8')
      // Sibling reference links become in-document anchors too.
      .replace(/\(([a-z-]+)\.md\)/g, '(#reference-$1)')
      // Demote headings by one level so the bundle has a single H1.
      .replace(/^(#+) /gm, '#$1 ')
    parts.push('', '---', '', `<a id="reference-${name}"></a>`, '', text)
  }

  const out = parts.join('\n').replace(/\n{4,}/g, '\n\n\n')
  const target = join(dir, `${skill}.bundle.md`)

  if (checkOnly) {
    const current = existsSync(target) ? readFileSync(target, 'utf8') : ''
    if (current !== out) {
      stale++
      console.log(`FAIL bundle ${skill}/${skill}.bundle.md is stale, run: make bundle`)
    } else {
      console.log(`ok   bundle ${skill}/${skill}.bundle.md is current`)
    }
  } else {
    writeFileSync(target, out)
    console.log(`wrote ${skill}/${skill}.bundle.md (${out.length} bytes, ${refs.length} references)`)
  }
}

process.exit(stale ? 1 : 0)
