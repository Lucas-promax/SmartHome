import test from 'node:test'
import assert from 'node:assert/strict'
import { renderMarkdown } from '../src/utils/markdown.js'

test('renders headings, emphasis, lists, tables and code blocks', () => {
  const html = renderMarkdown('# Status\n\n**Ready**\n\n- Door\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```json\n{"ok":true}\n```')
  for (const tag of ['<h1>', '<strong>', '<ul>', '<table>', '<pre>', 'language-json']) assert.ok(html.includes(tag))
})

test('escapes raw HTML, blocks script links and remote images', () => {
  const html = renderMarkdown('<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n![x](https://example.com/tracker.png)')
  assert.ok(!html.includes('<script>'))
  assert.ok(!html.includes('href="javascript:'))
  assert.ok(!html.includes('<img'))
  assert.ok(html.includes('&lt;script&gt;'))
})

test('links open safely and unfinished streamed Markdown renders', () => {
  const html = renderMarkdown('[Docs](https://example.com)')
  assert.ok(html.includes('target="_blank"'))
  assert.ok(html.includes('rel="noopener noreferrer"'))
  assert.doesNotThrow(() => renderMarkdown('```json\n{"ok":'))
  assert.equal(renderMarkdown(''), '')
})
