'use client';

import { useState, useRef, useEffect } from 'react';

interface Message {
    role: 'user' | 'assistant';
    content: string;
}

interface ACPContract {
    intent: string;
    action: string;
    verification: string;
    execution: string;
    timestamp: string;
}

interface CheckoutData {
    id: string;
    status: string;
    line_items: Array<{
        id: string;
        item: { id: string; quantity: number };
        subtotal: number;
        tax: number;
        total: number;
    }>;
    totals: Array<{
        type: string;
        display_text: string;
        amount: number;
    }>;
    fulfillment_options: Array<{
        id: string;
        title: string;
        subtitle?: string;
        total: number;
    }>;
    fulfillment_option_id?: string;
    order?: {
        id: string;
        permalink_url?: string;
    };
}

const WELCOME_MESSAGE: Message = {
    role: 'assistant',
    content:
        "Welcome! I'm your AI shopping assistant. I can help you find and purchase products from our catalog.\n\nTry saying something like:\n• \"Show me dining tables\"\n• \"I'm looking for a blue sofa under $1000\"\n• \"What lighting options do you have?\"",
};

export default function Home() {
    const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [checkout, setCheckout] = useState<CheckoutData | null>(null);
    const [acpContracts, setAcpContracts] = useState<ACPContract[]>([]);
    const [showContracts, setShowContracts] = useState(true);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const sendMessage = async () => {
        if (!input.trim() || isLoading) return;

        const userMessage = input.trim();
        setInput('');
        setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
        setIsLoading(true);

        // Add ACP contract for this interaction
        const newContract: ACPContract = {
            intent: detectIntent(userMessage),
            action: 'Processing...',
            verification: 'Pending',
            execution: 'Pending',
            timestamp: new Date().toISOString(),
        };
        setAcpContracts((prev) => [...prev, newContract]);

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userMessage }),
            });

            if (!res.ok) throw new Error('Chat request failed');

            const data = await res.json();
            setMessages((prev) => [...prev, { role: 'assistant', content: data.response }]);

            // Update ACP contract
            setAcpContracts((prev) =>
                prev.map((c, i) =>
                    i === prev.length - 1
                        ? { ...c, action: 'Completed', verification: 'Approved', execution: 'Success' }
                        : c
                )
            );

            if (data.checkout_session_id) {
                fetchCheckoutSession(data.checkout_session_id);
            }
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: 'Sorry, I encountered an error. Please make sure the agent service is running on port 8003.',
                },
            ]);
            // Update contract with error
            setAcpContracts((prev) =>
                prev.map((c, i) =>
                    i === prev.length - 1
                        ? { ...c, action: 'Failed', verification: 'Rejected', execution: 'Error' }
                        : c
                )
            );
        } finally {
            setIsLoading(false);
        }
    };

    const detectIntent = (message: string): string => {
        const lower = message.toLowerCase();
        if (lower.includes('buy') || lower.includes('purchase') || lower.includes('checkout')) {
            return '🛒 Purchase';
        } else if (lower.includes('compare')) {
            return '⚖️ Compare';
        } else if (lower.includes('show') || lower.includes('find') || lower.includes('search')) {
            return '🔍 Search';
        } else {
            return '💬 Query';
        }
    };

    const fetchCheckoutSession = async (sessionId: string) => {
        try {
            const res = await fetch(`/api/seller/checkout_sessions/${sessionId}`);
            if (res.ok) {
                const data = await res.json();
                setCheckout(data);
            }
        } catch (err) {
            // Silently fail — checkout panel just won't update
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    const formatPrice = (cents: number) => {
        return `$${(cents / 100).toFixed(2)}`;
    };

    const renderMessageContent = (content: string) => {
        // Check if content has product listings (markdown format)
        const lines = content.split('\n');
        const hasProductCards = content.includes('**ID**:') || content.includes('- **ID**:');

        if (!hasProductCards) {
            return <div style={{ whiteSpace: 'pre-wrap' }}>{content}</div>;
        }

        // Parse products from markdown
        const products: any[] = [];
        let currentProduct: any = {};

        lines.forEach((line) => {
            if (line.match(/^###?\s+\d+\.\s+\*\*/)) {
                // New product header
                if (currentProduct.name) {
                    products.push(currentProduct);
                }
                const nameMatch = line.match(/\*\*(.+?)\*\*/);
                currentProduct = { name: nameMatch?.[1] || '' };
            } else if (line.includes('- **ID**:') || line.includes('**ID**:')) {
                const idMatch = line.match(/\*\*ID\*\*:\s*(\S+)/);
                currentProduct.id = idMatch?.[1];
            } else if (line.includes('- **Price**:') || line.includes('**Price**:')) {
                const priceMatch = line.match(/\$[\d,]+\.?\d*/);
                currentProduct.price = priceMatch?.[0];
            } else if (line.includes('- **Description**:') || line.includes('**Description**:')) {
                const descMatch = line.match(/\*\*Description\*\*:\s*(.+)/);
                currentProduct.description = descMatch?.[1];
            } else if (line.includes('- **Rating**:') || line.includes('**Rating**:') || line.includes('**Average Rating**:')) {
                const ratingMatch = line.match(/([\d.]+)\s*\(/);
                currentProduct.rating = ratingMatch?.[1];
            }
        });

        if (currentProduct.name) {
            products.push(currentProduct);
        }

        if (products.length === 0) {
            return <div style={{ whiteSpace: 'pre-wrap' }}>{content}</div>;
        }

        // Render as product cards
        return (
            <div>
                <div style={{ marginBottom: '12px', whiteSpace: 'pre-wrap' }}>
                    {content.split('\n\n')[0]}
                </div>
                <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
                    {products.map((product, idx) => (
                        <div
                            key={idx}
                            style={{
                                border: '1px solid var(--border)',
                                borderRadius: '8px',
                                padding: '16px',
                                backgroundColor: 'var(--bg-secondary)',
                                transition: 'transform 0.2s, box-shadow 0.2s',
                                cursor: 'pointer',
                            }}
                            onMouseEnter={(e) => {
                                e.currentTarget.style.transform = 'translateY(-2px)';
                                e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)';
                            }}
                            onMouseLeave={(e) => {
                                e.currentTarget.style.transform = 'translateY(0)';
                                e.currentTarget.style.boxShadow = 'none';
                            }}
                        >
                            <div style={{ fontWeight: 600, fontSize: '16px', marginBottom: '8px', color: 'var(--text-primary)' }}>
                                {product.name}
                            </div>
                            {product.id && (
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                                    ID: <span style={{ fontFamily: 'monospace', background: 'var(--bg-tertiary)', padding: '2px 6px', borderRadius: '4px' }}>{product.id}</span>
                                </div>
                            )}
                            {product.price && (
                                <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--accent)', marginBottom: '8px' }}>
                                    {product.price}
                                </div>
                            )}
                            {product.rating && (
                                <div style={{ fontSize: '14px', marginBottom: '8px' }}>
                                    ⭐ {product.rating}
                                </div>
                            )}
                            {product.description && (
                                <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.4', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical' }}>
                                    {product.description}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    const getStatusSteps = () => {
        const steps = ['not_ready_for_payment', 'ready_for_payment', 'in_progress', 'completed'];
        const currentIdx = checkout ? steps.indexOf(checkout.status) : -1;
        return steps.map((step, idx) => ({
            step,
            active: idx === currentIdx,
            completed: idx < currentIdx,
        }));
    };

    return (
        <div className="app-container">
            {/* ── Chat Panel ────────────────────────────── */}
            <div className="panel chat-panel">
                <div className="panel-header">
                    <h2>🤖 Commerce Agent</h2>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <button
                            onClick={() => setShowContracts(!showContracts)}
                            style={{
                                padding: '4px 12px',
                                fontSize: '12px',
                                background: showContracts ? 'var(--accent)' : 'var(--bg-secondary)',
                                color: showContracts ? 'white' : 'var(--text-secondary)',
                                border: '1px solid var(--border)',
                                borderRadius: '4px',
                                cursor: 'pointer',
                            }}
                        >
                            {showContracts ? 'Hide' : 'Show'} ACP Flow
                        </button>
                        <span className="badge badge-accent">ACP v1</span>
                    </div>
                </div>

                {/* ── ACP Contract Flow ────────────────────────────── */}
                {showContracts && acpContracts.length > 0 && (
                    <div style={{
                        padding: '12px',
                        background: 'var(--bg-secondary)',
                        borderBottom: '1px solid var(--border)',
                        maxHeight: '200px',
                        overflowY: 'auto',
                    }}>
                        <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '8px', color: 'var(--text-secondary)' }}>
                            📋 ACP Contract Flow (Intent → Action → Verification → Execution)
                        </div>
                        {acpContracts.slice(-3).map((contract, idx) => (
                            <div
                                key={idx}
                                style={{
                                    background: 'var(--bg-primary)',
                                    border: '1px solid var(--border)',
                                    borderRadius: '6px',
                                    padding: '10px',
                                    marginBottom: '8px',
                                    fontSize: '11px',
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                                    <span style={{ fontWeight: 600 }}>{contract.intent}</span>
                                    <span style={{ color: 'var(--text-secondary)', fontSize: '10px' }}>
                                        {new Date(contract.timestamp).toLocaleTimeString()}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                    <div style={{
                                        padding: '4px 8px',
                                        borderRadius: '4px',
                                        background: contract.action === 'Completed' ? '#10b98133' : '#94a3b833',
                                        border: `1px solid ${contract.action === 'Completed' ? '#10b981' : '#94a3b8'}`,
                                        fontSize: '10px',
                                    }}>
                                        Action: {contract.action}
                                    </div>
                                    <div style={{
                                        padding: '4px 8px',
                                        borderRadius: '4px',
                                        background: contract.verification === 'Approved' ? '#10b98133' : '#94a3b833',
                                        border: `1px solid ${contract.verification === 'Approved' ? '#10b981' : '#94a3b8'}`,
                                        fontSize: '10px',
                                    }}>
                                        Verify: {contract.verification}
                                    </div>
                                    <div style={{
                                        padding: '4px 8px',
                                        borderRadius: '4px',
                                        background: contract.execution === 'Success' ? '#10b98133' : contract.execution === 'Error' ? '#ef444433' : '#94a3b833',
                                        border: `1px solid ${contract.execution === 'Success' ? '#10b981' : contract.execution === 'Error' ? '#ef4444' : '#94a3b8'}`,
                                        fontSize: '10px',
                                    }}>
                                        Execute: {contract.execution}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                <div className="messages-container">
                    {messages.map((msg, i) => (
                        <div key={i} className="message">
                            <div className={`message-avatar ${msg.role}`}>
                                {msg.role === 'user' ? '👤' : '🛒'}
                            </div>
                            <div className="message-content">
                                <div className="message-role">{msg.role}</div>
                                <div className="message-text">
                                    {renderMessageContent(msg.content)}
                                </div>
                            </div>
                        </div>
                    ))}

                    {isLoading && (
                        <div className="message">
                            <div className="message-avatar assistant">🛒</div>
                            <div className="message-content">
                                <div className="message-role">Assistant</div>
                                <div className="typing-indicator">
                                    <div className="typing-dot" />
                                    <div className="typing-dot" />
                                    <div className="typing-dot" />
                                </div>
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>

                <div className="chat-input-container">
                    <div className="chat-input-wrapper">
                        <textarea
                            ref={inputRef}
                            className="chat-input"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Ask about products, start a checkout..."
                            rows={1}
                        />
                        <button
                            className="send-button"
                            onClick={sendMessage}
                            disabled={isLoading || !input.trim()}
                        >
                            Send
                        </button>
                    </div>
                </div>
            </div>

            {/* ── Checkout Panel ────────────────────────── */}
            <div className="panel checkout-panel">
                <div className="panel-header">
                    <h2>🧾 Checkout</h2>
                    {checkout && (
                        <span
                            className={`badge ${checkout.status === 'completed'
                                    ? 'badge-success'
                                    : checkout.status === 'ready_for_payment'
                                        ? 'badge-accent'
                                        : 'badge-warning'
                                }`}
                        >
                            {checkout.status.replace(/_/g, ' ')}
                        </span>
                    )}
                </div>

                <div className="checkout-content">
                    {!checkout ? (
                        <div className="checkout-empty">
                            <div className="checkout-empty-icon">🛍️</div>
                            <h3>No Active Checkout</h3>
                            <p>
                                Chat with the agent to search for products and start a checkout session.
                            </p>
                        </div>
                    ) : (
                        <>
                            {/* Status Timeline */}
                            <div className="status-timeline">
                                {getStatusSteps().map((s, i) => (
                                    <div
                                        key={i}
                                        className={`status-step ${s.active ? 'active' : ''} ${s.completed ? 'completed' : ''
                                            }`}
                                    />
                                ))}
                            </div>

                            {/* Line Items */}
                            {checkout.line_items.length > 0 && (
                                <div className="checkout-section">
                                    <div className="checkout-section-title">Items</div>
                                    {checkout.line_items.map((li) => (
                                        <div key={li.id} className="line-item">
                                            <div>
                                                <div className="line-item-name">{li.item.id}</div>
                                                <div className="line-item-qty">Qty: {li.item.quantity}</div>
                                            </div>
                                            <div className="line-item-price">{formatPrice(li.total)}</div>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Fulfillment Options */}
                            {checkout.fulfillment_options.length > 0 && (
                                <div className="checkout-section">
                                    <div className="checkout-section-title">Shipping</div>
                                    {checkout.fulfillment_options.map((opt) => (
                                        <div
                                            key={opt.id}
                                            className={`fulfillment-option ${checkout.fulfillment_option_id === opt.id ? 'selected' : ''
                                                }`}
                                        >
                                            <div className="fulfillment-option-title">{opt.title}</div>
                                            {opt.subtitle && (
                                                <div className="fulfillment-option-subtitle">{opt.subtitle}</div>
                                            )}
                                            <div className="fulfillment-option-price">{formatPrice(opt.total)}</div>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Totals */}
                            {checkout.totals.length > 0 && (
                                <div className="checkout-section">
                                    <div className="checkout-section-title">Summary</div>
                                    {checkout.totals.map((total, i) => (
                                        <div
                                            key={i}
                                            className={`total-row ${total.type === 'total' ? 'grand-total' : ''}`}
                                        >
                                            <span>{total.display_text}</span>
                                            <span>{formatPrice(total.amount)}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Order Confirmation */}
                            {checkout.order && (
                                <div className="checkout-section">
                                    <div className="checkout-section-title">Order Confirmed</div>
                                    <div className="line-item" style={{ borderColor: 'var(--success)' }}>
                                        <div>
                                            <div className="line-item-name">✅ {checkout.order.id}</div>
                                            <div className="line-item-qty">Thank you for your purchase!</div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
