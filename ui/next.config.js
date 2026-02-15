/** @type {import('next').NextConfig} */
const nextConfig = {
    async rewrites() {
        return [
            {
                source: '/api/chat',
                destination: 'http://localhost:8003/chat',
            },
            {
                source: '/api/seller/:path*',
                destination: 'http://localhost:8001/:path*',
            },
        ];
    },
};

module.exports = nextConfig;
