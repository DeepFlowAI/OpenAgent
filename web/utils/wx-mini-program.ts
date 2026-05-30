const WEIXIN_MINI_PROGRAM_PREFIX = 'weixin://'
const WX_SDK_URL = 'https://res.wx.qq.com/open/js/jweixin-1.3.2.js'

type WxMiniProgram = {
  navigateTo: (options: { url: string }) => void
  getEnv: (callback: (res: { miniprogram: boolean }) => void) => void
}

declare global {
  interface Window {
    wx?: {
      miniProgram?: WxMiniProgram
    }
  }
}

let wxSdkPromise: Promise<void> | null = null
let miniProgramEnvPromise: Promise<boolean> | null = null

export function isWeixinMiniProgramUrl(url: string) {
  return url.trim().startsWith(WEIXIN_MINI_PROGRAM_PREFIX)
}

function loadWxSdk() {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('WeChat SDK is only available in browser'))
  }

  if (window.wx?.miniProgram) return Promise.resolve()
  if (wxSdkPromise) return wxSdkPromise

  wxSdkPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.type = 'text/javascript'
    script.src = WX_SDK_URL
    script.onload = () => resolve()
    script.onerror = () => {
      wxSdkPromise = null
      reject(new Error('Failed to load WeChat SDK'))
    }
    document.head.appendChild(script)
  })

  return wxSdkPromise
}

export async function checkMiniProgram() {
  if (miniProgramEnvPromise) return miniProgramEnvPromise

  miniProgramEnvPromise = (async () => {
    try {
      await loadWxSdk()
      const miniProgram = window.wx?.miniProgram
      if (!miniProgram) return false

      return await new Promise<boolean>((resolve) => {
        miniProgram.getEnv((res) => resolve(Boolean(res.miniprogram)))
      })
    } catch {
      return false
    }
  })()

  return miniProgramEnvPromise
}

export function toMiniProgramPath(url: string) {
  const path = url.trim().replace(/^weixin:\/\//, '')
  return path.startsWith('/') ? path : `/${path}`
}

export function navigateToMiniProgram(url: string) {
  if (typeof window === 'undefined') return false

  const miniProgram = window.wx?.miniProgram
  if (!miniProgram) return false

  miniProgram.navigateTo({ url: toMiniProgramPath(url) })
  return true
}

export async function openWeixinMiniProgramLink(
  url: string,
  onUnavailable?: () => void,
) {
  if (!isWeixinMiniProgramUrl(url)) return false

  if (await checkMiniProgram()) {
    return navigateToMiniProgram(url)
  }

  onUnavailable?.()
  return false
}
