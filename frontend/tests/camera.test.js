import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

function mountCamera(cameraApi, extra = {}) {
  const source = fs.readFileSync(new URL('../src/components/CameraView.vue', import.meta.url), 'utf8')
    .split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm, '')
  class Image {
    naturalWidth = 4
    naturalHeight = 3
    async decode() {}
  }
  let drawn
  const context = vm.createContext({
    cameraApi, Image, Date,
    ref: value => ({ value }), computed: fn => ({ get value() { return fn() } }),
    defineProps: () => ({ detections: [] }), defineEmits: () => () => {}, defineExpose() {},
    onMounted() {}, onUnmounted() {}, watch() {}, nextTick: async () => {},
    setTimeout: () => 1, clearTimeout() {}, navigator: {},
    document: { createElement: () => ({ getContext: () => ({ drawImage: image => { drawn = image } }),
      toDataURL: () => drawn.src }) }, ...extra
  })
  vm.runInContext(source + '\nglobalThis.api = { startCamera, stopCamera, pollSerialFrame, captureFrame, refreshCameras, changeCamera, selectedCameraId, serialImage, cameraEnabled, boardCameras, errorMessage };', context)
  return context.api
}

async function settle() {
  for (let i = 0; i < 15; i++) await Promise.resolve()
}

test('board USB works without browser camera support and refuses stale or disconnected captures', async () => {
  let result = { connected: true, fresh: true, age_seconds: 0, frame_id: 1, data_url: 'usb-frame' }
  const connected = [], disconnected = []
  const a = mountCamera({
    ports: async () => [],
    usbDevices: async () => [{ device: '/dev/video0', name: 'HD USB CAMERA', accessible: true }],
    connectUsb: async device => { connected.push(device); return { session: 'usb-session' } },
    frame: async () => result,
    disconnect: async session => disconnected.push(session)
  })
  await a.refreshCameras()
  assert.equal(a.selectedCameraId.value, 'board-usb:/dev/video0')
  await a.startCamera()
  await settle()
  assert.deepEqual(connected, ['/dev/video0'])
  assert.equal(a.cameraEnabled.value, true)
  assert.equal(a.serialImage.value, 'usb-frame')
  assert.equal(a.captureFrame(), 'usb-frame')

  result = { ...result, data_url: null }
  await a.pollSerialFrame('usb-session')
  assert.equal(a.captureFrame(), 'usb-frame')
  assert.equal(a.serialImage.value, 'usb-frame')

  result = { ...result, age_seconds: 11, fresh: false }
  await a.pollSerialFrame('usb-session')
  assert.equal(a.cameraEnabled.value, false)
  assert.equal(a.captureFrame(), null)
  assert.equal(a.serialImage.value, '')

  result = { connected: false, fresh: false, error: 'USB unplugged' }
  await a.pollSerialFrame('usb-session')
  assert.match(a.errorMessage.value, /USB unplugged/)
  assert.equal(a.captureFrame(), null)
  assert.deepEqual(disconnected, ['usb-session'])
})

test('device refresh keeps board selection and respects an explicit browser camera selection', async () => {
  const a = mountCamera({
    ports: async () => [],
    usbDevices: async () => [{ device: '/dev/video0', name: 'HD USB CAMERA', accessible: true }]
  }, { navigator: { mediaDevices: { enumerateDevices: async () => [{ kind: 'videoinput', deviceId: 'pc-camera' }] } } })
  await a.refreshCameras()
  await a.refreshCameras()
  assert.equal(a.selectedCameraId.value, 'board-usb:/dev/video0')
  a.selectedCameraId.value = ''
  a.changeCamera()
  await a.refreshCameras()
  assert.equal(a.selectedCameraId.value, '')
})

test('a USB connection completed after closing the camera is released', async () => {
  let finish
  const disconnected = []
  const a = mountCamera({
    connectUsb: () => new Promise(resolve => { finish = resolve }),
    disconnect: async session => disconnected.push(session)
  })
  a.selectedCameraId.value = 'board-usb:/dev/video0'
  const starting = a.startCamera()
  await settle()
  await a.stopCamera()
  finish({ session: 'late-usb-session' })
  await starting
  assert.equal(a.cameraEnabled.value, false)
  assert.equal(a.captureFrame(), null)
  assert.deepEqual(disconnected, ['late-usb-session'])
})

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
