# ACP Framework Examples

This directory contains examples showing how to use the `acp-framework` package.

## Installation

First, install the framework:

```bash
# From GitHub
pip install git+https://github.com/shabazpatel/acp-infra.git

# Or locally
cd acp-infra
pip install -e .
```

## Examples

### 1. Simple Merchant (`simple_merchant.py`)

A minimal ACP-compliant merchant showing the core pattern.

**Run it:**
```bash
python examples/simple_merchant.py
```

**What it demonstrates:**
- Installing and importing `acp-framework`
- Implementing `ACPSellerAdapter` with required methods
- Mounting the ACP router in FastAPI
- Getting 5 ACP endpoints automatically

**Try it:**
```bash
# Create a checkout session
curl -X POST http://localhost:8000/checkout_sessions \
  -H "Content-Type: application/json" \
  -H "API-Version: 2026-01-30" \
  -d '{"items": [{"id": "test-product", "quantity": 1}]}'
```

### 2. Full Implementation

For a complete, production-ready example with database integration, see the main services:
- [services/seller/main.py](../services/seller/main.py) - Full Wayfair demo implementation
- Shows database integration, search, catalog ingestion, etc.

## Next Steps

1. **Study the simple example** - Understand the adapter pattern
2. **Review the full implementation** - See production patterns
3. **Build your adapter** - Implement for your own catalog/systems
4. **Test with agents** - Use the demo agent or build your own

## Resources

- [CONTRIBUTION_HELPER.md](../CONTRIBUTION_HELPER.md) - Understand the codebase
- [README.md](../README.md) - Project overview and setup
- [ACP Spec](https://docs.google.com/document/d/1...) - Protocol specification
