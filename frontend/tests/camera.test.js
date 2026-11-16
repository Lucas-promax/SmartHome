import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

test('progressive previews never replace the complete capture image', async () => {
  const source = fs.readFileSync(new URL('../src/components/CameraView.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  let result = { connected: true, fresh: false, preview_fresh: true,
    preview_id: 1, preview: { data_url: 'partial-one', rows: 1, height: 3 } }
  const disconnected = []
  const cameraApi = {
    connect: async () => ({ session: 'test-session' }),
    disconnect: async session => disconnected.push(session),
    frame: async () => result
  }
  class Image {
    naturalWidth = 2
    naturalHeight = 3
    async decode() {}
  }
  let drawn
  const context = vm.createContext({
    cameraApi, Image, Date,
    ref: value => ({ value }), computed: fn => ({ get value() { return fn() } }),
    defineProps: () => ({ detections: [] }), defineEmits: () => () => {}, defineExpose() {},
    onMounted() {}, onUnmounted() {}, watch() {}, nextTick: async () => {},
    setTimeout: () => 1, clearTimeout() {},
    navigator: { mediaDevices: {} },
    document: { createElement: () => ({ getContext: () => ({ drawImage: image => { drawn = image } }),
      toDataURL: () => drawn.src }) }
  })
  vm.runInContext(source + '\nglobalThis.api = { startCamera, stopCamera, pollSerialFrame, captureFrame, selectedCameraId, serialImage, serialProgress, cameraEnabled };', context)
  const a = context.api
  a.selectedCameraId.value = 'ov7670:COM7'
  await a.startCamera()
  for (let i = 0; i < 10; i++) await Promise.resolve()
  assert.equal(a.serialImage.value, 'partial-one')
  assert.equal(a.serialProgress.value, 33)
  assert.equal(a.cameraEnabled.value, false)
  assert.equal(a.captureFrame(), null)

  result = { connected: true, fresh: true, frame_id: 1, age_seconds: 0,
    data_url: 'complete-one', preview_fresh: true, preview_id: 2,
    preview: { data_url: 'complete-one', rows: 3, height: 3 } }
  await a.pollSerialFrame('test-session')
  assert.equal(a.captureFrame(), 'complete-one')

  result = { ...result, data_url: null, preview_id: 3,
    preview: { data_url: 'partial-two', rows: 1, height: 3 } }
  await a.pollSerialFrame('test-session')
  assert.equal(a.serialImage.value, 'partial-two')
  assert.equal(a.captureFrame(), 'complete-one')

  result = { ...result, age_seconds: 11, preview_fresh: false, preview: null }
  await a.pollSerialFrame('test-session')
  assert.equal(a.captureFrame(), null)
  assert.equal(a.serialImage.value, '')
  await a.stopCamera()
  assert.deepEqual(disconnected, ['test-session'])
})
