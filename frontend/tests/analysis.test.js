import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

test('analytics presets follow board time and custom ranges remain explicit', async () => {
  const source = fs.readFileSync(new URL('../src/views/DataAnalysis.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  const requests = []
  const result = {
    server_time: '2026-07-10T16:40:00+08:00',
    range: { after: '2026-07-10T10:40:00+08:00', before: '2026-07-10T16:40:00+08:00' },
    sensors: { raw_count: 1159 }
  }
  class BrowserDate extends Date {
    static now() { return Date.parse('2026-11-17T20:00:00+08:00') }
  }
  const context = vm.createContext({
    ref: value => ({ value }), computed: fn => ({ get value() { return fn() } }), onMounted() {},
    analysisApi: { overview: async params => { requests.push(JSON.parse(JSON.stringify(params))); return result } },
    ElMessage: { error(message) { throw new Error(message) } }, Date: BrowserDate
  })
  vm.runInContext(source + '\nglobalThis.api = { timeRange, customRange, rangeParams, loadData, onCustomRange, clockMismatch, queryRangeLabel, analysis };', context)
  const a = context.api
  for (const [preset, seconds] of [['30m', 1800], ['6h', 21600], ['24h', 86400], ['7d', 604800]]) {
    a.timeRange.value = preset
    await a.loadData()
    assert.deepEqual(requests.at(-1), { window_seconds: seconds })
  }
  assert.equal(a.analysis.value.sensors.raw_count, 1159)
  assert.equal(a.clockMismatch.value, true)
  assert.match(a.queryRangeLabel.value, /2026/)
  assert.match(a.queryRangeLabel.value, /7\/10|07\/10|7月10/)

  a.customRange.value = ['2026-07-10T16:00:00+08:00', '2026-07-10T17:00:00+08:00']
  await a.loadData()
  assert.deepEqual(requests.at(-1), { after: a.customRange.value[0], before: a.customRange.value[1] })
  a.customRange.value = null
  a.onCustomRange(null)
  await Promise.resolve()
  assert.equal(a.timeRange.value, '6h')
  assert.deepEqual(requests.at(-1), { window_seconds: 21600 })

  result.server_time = '2026-11-17T20:00:00+08:00'
  assert.equal(a.clockMismatch.value, false)
})
