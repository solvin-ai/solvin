// next.config.js

/** @type {import('next').NextConfig} */
module.exports = {
  async rewrites() {
    return [
      {
        source: '/api/v1/configs/:path*',
        destination: `${process.env.NEXT_PUBLIC_SERVICE_URL_CONFIGS}/api/${process.env.NEXT_PUBLIC_API_VERSION}/configs/:path*`
      },
      {
        source: '/api/v1/agents/:path*',
        destination: `${process.env.NEXT_PUBLIC_SERVICE_URL_AGENTS}/api/${process.env.NEXT_PUBLIC_API_VERSION}/agents/:path*`
      },
      {
        source: '/api/v1/messages/:path*',
        destination: `${process.env.NEXT_PUBLIC_SERVICE_URL_AGENTS}/api/${process.env.NEXT_PUBLIC_API_VERSION}/messages/:path*`
      },
      {
        source: '/api/v1/turns/:path*',
        destination: `${process.env.NEXT_PUBLIC_SERVICE_URL_AGENTS}/api/${process.env.NEXT_PUBLIC_API_VERSION}/turns/:path*`
      },
      {
        source: '/api/v1/templates/:path*',
        destination: '/api/templates/:path*'
      }
    ]
  }
}
