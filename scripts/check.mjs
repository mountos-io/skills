// Repository self-check. Run with `make check` (needs node or bun, and jsdom + mermaid).
//
// Verifies, for every skill directory (any directory holding a SKILL.md):
//   1. every mermaid diagram parses
//   2. every relative link resolves to a file that exists
//   3. the version agrees across VERSION, skill.json, and the SKILL.md frontmatter
//   4. the frontmatter name matches the directory name
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs'
import { join, dirname, resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

let failures = 0
const fail = (msg) => { failures++; console.log(`FAIL ${msg}`) }
const pass = (msg) => console.log(`ok   ${msg}`)

const skills = readdirSync(root, { withFileTypes: true })
  .filter((d) => d.isDirectory() && !d.name.startsWith('.') &&
    !['node_modules', 'scripts'].includes(d.name) &&
    existsSync(join(root, d.name, 'SKILL.md')))
  .map((d) => d.name)

if (skills.length === 0) fail('no skill directory contains a SKILL.md')
else pass(`found skills: ${skills.join(', ')}`)

// Collect every markdown file, repo-root docs plus each skill tree.
const docs = []
const walk = (dir) => {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith('.') || e.name === 'node_modules') continue
    const p = join(dir, e.name)
    if (e.isDirectory()) walk(p)
    else if (e.name.endsWith('.md')) docs.push(relative(root, p))
  }
}
walk(root)

// 1. mermaid
const { JSDOM } = await import('jsdom')
const dom = new JSDOM('<!doctype html><html><body></body></html>')
for (const k of ['window', 'document', 'navigator', 'Element', 'Node', 'HTMLElement',
  'SVGElement', 'NodeFilter', 'getComputedStyle', 'DocumentFragment',
  'MutationObserver', 'trustedTypes']) {
  const v = k === 'window' ? dom.window : dom.window[k]
  if (v !== undefined) globalThis[k] = v
}
const mermaid = (await import('mermaid')).default
for (const f of docs) {
  const blocks = [...readFileSync(join(root, f), 'utf8').matchAll(/```mermaid\n([\s\S]*?)```/g)]
  for (const [i, m] of blocks.entries()) {
    try {
      await mermaid.parse(m[1])
      pass(`diagram ${f} #${i + 1}`)
    } catch (e) {
      fail(`diagram ${f} #${i + 1}: ${String(e.message ?? e).split('\n')[0]}`)
    }
  }
}

// 2. relative links
for (const f of docs) {
  for (const m of readFileSync(join(root, f), 'utf8').matchAll(/\]\(([^)#\s]+)(?:#[^)\s]*)?\)/g)) {
    const target = m[1]
    if (/^(https?:|mailto:)/.test(target)) continue
    const abs = resolve(join(root, dirname(f)), target)
    if (existsSync(abs)) pass(`link ${f} -> ${target}`)
    else fail(`link ${f} -> ${target} does not exist`)
  }
}

// 3 and 4. per-skill version and name agreement
for (const s of skills) {
  const dir = join(root, s)
  const read = (n) => readFileSync(join(dir, n), 'utf8')
  try {
    const version = read('VERSION').trim()
    const manifest = JSON.parse(read('skill.json'))
    const front = read('SKILL.md').match(/^version:\s*(\S+)\s*$/m)?.[1]
    const frontName = read('SKILL.md').match(/^name:\s*(\S+)\s*$/m)?.[1]
    // plugin.json is the Claude Code manifest. Optional, but when present it must
    // agree, or a plugin install ships a version that disagrees with the content.
    const pluginPath = join(dir, '.claude-plugin', 'plugin.json')
    const plugin = existsSync(pluginPath) ? JSON.parse(readFileSync(pluginPath, 'utf8')) : null

    const versions = { VERSION: version, 'skill.json': manifest.version, 'SKILL.md': front }
    if (plugin) versions['plugin.json'] = plugin.version
    const disagree = Object.entries(versions).filter(([, v]) => v !== version)
    if (disagree.length === 0) pass(`${s}: version ${version} agrees across ${Object.keys(versions).length} files`)
    else fail(`${s}: version mismatch ${disagree.map(([k, v]) => `${k}=${v}`).join(' ')} (expected ${version})`)

    const names = { 'SKILL.md': frontName, 'skill.json': manifest.name }
    if (plugin) names['plugin.json'] = plugin.name
    const badNames = Object.entries(names).filter(([, v]) => v !== s)
    if (badNames.length === 0) pass(`${s}: name matches directory`)
    else fail(`${s}: name mismatch ${badNames.map(([k, v]) => `${k}=${v}`).join(' ')} (expected ${s})`)
    for (const r of manifest.references ?? []) {
      if (existsSync(join(dir, r))) pass(`${s}: manifest reference ${r}`)
      else fail(`${s}: manifest lists missing reference ${r}`)
    }
  } catch (e) {
    fail(`${s}: ${String(e.message ?? e)}`)
  }
}

console.log(failures ? `\n${failures} check(s) failed` : '\nall checks passed')
process.exit(failures ? 1 : 0)
