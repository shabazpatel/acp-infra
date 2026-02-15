import { NextRequest, NextResponse } from 'next/server';

const AGENT_URL = process.env.AGENT_SERVICE_URL || 'http://localhost:8003';

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();
        const { message, user_id = 'demo-user', session_id } = body;

        if (!message) {
            return NextResponse.json(
                { error: 'Message is required' },
                { status: 400 }
            );
        }

        // Forward to agent service
        const agentResponse = await fetch(`${AGENT_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message,
                user_id,
                session_id,
            }),
        });

        if (!agentResponse.ok) {
            throw new Error(`Agent service returned ${agentResponse.status}`);
        }

        const data = await agentResponse.json();

        return NextResponse.json({
            response: data.response,
            session_id: data.session_id,
            checkout_session_id: data.checkout_session_id,
        });
    } catch (error) {
        console.error('Chat API error:', error);
        return NextResponse.json(
            {
                error: 'Failed to communicate with agent service',
                details: error instanceof Error ? error.message : 'Unknown error',
            },
            { status: 500 }
        );
    }
}