import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
    title: 'ACP Demo — Agentic Commerce Protocol',
    description: 'Interactive demo of the Agentic Commerce Protocol with AI-powered shopping',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en">
            <head>
                <link
                    href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
                    rel="stylesheet"
                />
            </head>
            <body>{children}</body>
        </html>
    );
}
