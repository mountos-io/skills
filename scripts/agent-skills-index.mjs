// Prints the Agent Skills discovery fragment for this repo: one skill-md entry per
// <skill>/SKILL.md. Digests cover the committed bytes that raw.githubusercontent.com serves,
// so run it on a clean checkout of main.
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const base = 'https://raw.githubusercontent.com/mountos-io/skills/main'

function frontmatter(file, text) {
  const m = text.match(/^---\n([\s\S]*?)\n---/)
  if (!m) throw new Error(`${file}: missing frontmatter`)
  const fields = {}
  for (const line of m[1].split('\n')) {
    const i = line.indexOf(':')
    if (i > 0) fields[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return fields
}

const skills = []
for (const entry of readdirSync(root, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
  if (!entry.isDirectory()) continue
  const file = join(root, entry.name, 'SKILL.md')
  if (!existsSync(file)) continue
  const bytes = readFileSync(file)
  const fm = frontmatter(file, bytes.toString('utf8'))
  if (fm.name !== entry.name) throw new Error(`${file}: frontmatter name "${fm.name}" differs from directory`)
  skills.push({
    name: fm.name,
    type: 'skill-md',
    description: fm.description,
    url: `${base}/${entry.name}/SKILL.md`,
    digest: `sha256:${createHash('sha256').update(bytes).digest('hex')}`,
  })
}

process.stdout.write(JSON.stringify({ skills }, null, 2) + '\n')
