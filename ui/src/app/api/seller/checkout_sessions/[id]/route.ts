import { NextRequest, NextResponse } from 'next/server';

const SELLER_URL = process.env.SELLER_SERVICE_URL || 'http://localhost:8001';
const AUTH_TOKEN = process.env.SELLER_AUTH_TOKEN || 'demo-token';

export async function GET(
    request: NextRequest,
    { params }: { params: { id: string } }
) {
    try {
        const sessionId = params.id;

        const sellerResponse = await fetch(
            `${SELLER_URL}/checkout_sessions/${sessionId}`,
            {
                headers: {
                    Authorization: `Bearer ${AUTH_TOKEN}`,
                    'Content-Type': 'application/json',
                    'API-Version': '2026-01-30',
                },
            }
        );

        if (!sellerResponse.ok) {
            if (sellerResponse.status === 404) {
                return NextResponse.json(
                    { error: 'Checkout session not found' },
                    { status: 404 }
                );
            }
            throw new Error(`Seller service returned ${sellerResponse.status}`);
        }

        const data = await sellerResponse.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error('Checkout API error:', error);
        return NextResponse.json(
            {
                error: 'Failed to fetch checkout session',
                details: error instanceof Error ? error.message : 'Unknown error',
            },
            { status: 500 }
        );
    }
}
