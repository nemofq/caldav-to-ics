/** @type {import('next').NextConfig} */

const nextConfig = {
    rewrites: async () => {
      return [
        {
          source: '/api/sync',
          destination:
            process.env.NODE_ENV === 'development'
              ? 'http://127.0.0.1:5328/api/sync'
              : '/api/sync',
        },
    ]
},
}

module.exports = nextConfig;