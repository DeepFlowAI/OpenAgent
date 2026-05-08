const fs = require('fs')
const path = require('path')

const envFile = `.env.${process.env.APP_ENV || 'dev'}`
const envPath = path.resolve(__dirname, envFile)
if (fs.existsSync(envPath)) {
  const lines = fs.readFileSync(envPath, 'utf-8').split('\n')
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const [key, ...rest] = trimmed.split('=')
    if (key && !process.env[key]) {
      process.env[key] = rest.join('=')
    }
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
}

module.exports = nextConfig
