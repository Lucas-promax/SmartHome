import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

function streamClient(chunks, contentType = 'text/event-stream') {
  const source = fs.readFileSync(new URL('../src/utils/http.js', import.meta.url), 'utf8')
    .split('// ============================================================')[0]
    .replace(/^export /gm, '').replace('import.meta.env.VITE_API_BASE_URL', 'undefined')
  const context = vm.createContext({
    TextDecoder,
    fetch: async () => new Response(new ReadableStream({ start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk)
      controller.close()
    } }), { headers: { 'Content-Type': contentType } })
  })
  vm.runInContext(source + '\nglobalThis.streamRequest = streamRequest;', context)
  return context.streamRequest
}

test('SSE handles UTF-8 fragmentation, CRLF frames and a final event without blank lines', async () => {
  const bytes = new TextEncoder().encode('data: {"type":"delta","content":"你好"}\r\n\r\ndata: {"type":"done"}')
  const chunks = []
  for (let i = 0; i < bytes.length; i += 7) chunks.push(bytes.slice(i, i + 7))
  const events = []
  await streamClient(chunks)('/agent/chat/stream', {}, event => events.push(event))
  assert.equal(events[0].content, '你好')
  assert.equal(events[1].type, 'done')
})

test('HTML, empty streams, premature EOF and backend errors cannot succeed silently', async () => {
  const fixtures = [
    ['<html>portal</html>', 'text/html', /未返回流式响应/],
    ['', 'text/event-stream', /提前结束/],
    ['data: {"type":"delta","content":"partial"}\n\n', 'text/event-stream', /提前结束/],
    ['data: {"type":"error","message":"需要校园网认证"}\n\n', 'text/event-stream', /需要校园网认证/]
  ]
  for (const [body, type, expected] of fixtures) {
    await assert.rejects(streamClient([new TextEncoder().encode(body)], type)('/agent/chat/stream', {}, () => {}), expected)
  }
})

test('confirmation and client tool requests terminate streams without requiring done', async () => {
  for (const type of ['confirm_required', 'client_tool_request']) {
    const events = []
    await streamClient([new TextEncoder().encode(`data: {"type":"${type}"}\n\n`)])('/agent/chat/stream', {}, event => events.push(event))
    assert.equal(events[0].type, type)
  }
})

test('assistant view reports a successful stream with no visible reply as an error', async () => {
  const source = fs.readFileSync(new URL('../src/views/SmartAssistant.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const context = vm.createContext({
    ref: value => ({ value }), computed: fn => ({ get value() { return fn() } }),
    onMounted() {}, nextTick: async () => {},
    agentApi: { streamChat: async (_payload, onEvent) => onEvent({ type: 'done' }) }
  })
  vm.runInContext(source + '\nglobalThis.runAssistantStream = runAssistantStream;', context)
  const assistant = { id: 'assistant', role: 'assistant', content: '', toolStatuses: [] }
  const conversation = { id: 'local-test', title: 'test', messages: [{ id: 'user', role: 'user', content: 'test' }, assistant] }
  await assert.rejects(context.runAssistantStream(conversation, assistant), /未返回回复正文/)
})
