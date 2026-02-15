#!/bin/bash
# ACP Sandbox Certification Tests
# Tests the seller and PSP services against ACP spec requirements

set -e

BASE_URL="http://localhost:8001"
PSP_URL="http://localhost:8002"
AUTH_HEADER="Authorization: Bearer demo-token"
CONTENT_TYPE="Content-Type: application/json"
API_VERSION="API-Version: 2026-01-30"

echo "=================================================="
echo "ACP SANDBOX CERTIFICATION TESTS"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results
PASS_COUNT=0
FAIL_COUNT=0

# Helper function to check test result
check_result() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"

    if [ "$actual" = "$expected" ]; then
        echo -e "${GREEN}✓ PASS${NC}: $test_name"
        ((PASS_COUNT++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}: $test_name"
        echo "  Expected: $expected"
        echo "  Got: $actual"
        ((FAIL_COUNT++))
        return 1
    fi
}

echo "=================================================="
echo "TEST 1: Session Creation"
echo "=================================================="
echo ""

# Test 1a: Create session WITHOUT address (should be not_ready_for_payment)
echo "→ Test 1a: Create session without address"
RESP1=$(curl -s -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-001" \
  -H "Request-Id: test-req-001" \
  -d '{"items":[{"id":"1","quantity":1}]}')

STATUS1=$(echo "$RESP1" | jq -r '.status // "ERROR"')
SESSION_ID1=$(echo "$RESP1" | jq -r '.id // "ERROR"')
check_result "Session without address has status not_ready_for_payment" "not_ready_for_payment" "$STATUS1"
echo "  Session ID: $SESSION_ID1"
echo ""

# Test 1b: Create session WITH address (should have fulfillment options)
echo "→ Test 1b: Create session with address"
RESP2=$(curl -s -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-002" \
  -H "Request-Id: test-req-002" \
  -d '{
    "items":[{"id":"1","quantity":1}],
    "fulfillment_address":{
      "name":"Test User",
      "line_one":"123 Main St",
      "city":"San Francisco",
      "state":"CA",
      "country":"US",
      "postal_code":"94105"
    }
  }')

SESSION_ID2=$(echo "$RESP2" | jq -r '.id // "ERROR"')
FULFILLMENT_COUNT=$(echo "$RESP2" | jq -r '.fulfillment_options | length')
HAS_TOTALS=$(echo "$RESP2" | jq -r 'if .totals | length > 0 then "true" else "false" end')
check_result "Session with address has fulfillment_options" "true" "$([ "$FULFILLMENT_COUNT" -gt 0 ] && echo 'true' || echo 'false')"
check_result "Session with address has totals array" "true" "$HAS_TOTALS"
echo "  Session ID: $SESSION_ID2"
echo "  Fulfillment options: $FULFILLMENT_COUNT"
echo ""

echo "=================================================="
echo "TEST 2: Shipping Option Update"
echo "=================================================="
echo ""

# Get the first fulfillment option ID
FULFILLMENT_ID=$(echo "$RESP2" | jq -r '.fulfillment_options[0].id')
echo "→ Updating session with fulfillment option: $FULFILLMENT_ID"

RESP3=$(curl -s -X POST "$BASE_URL/checkout_sessions/$SESSION_ID2" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-003" \
  -H "Request-Id: test-req-003" \
  -d "{\"fulfillment_option_id\":\"$FULFILLMENT_ID\"}")

UPDATED_STATUS=$(echo "$RESP3" | jq -r '.status // "ERROR"')
SELECTED_FULFILLMENT=$(echo "$RESP3" | jq -r '.fulfillment_option_id // "ERROR"')
check_result "Updated session has ready_for_payment status" "ready_for_payment" "$UPDATED_STATUS"
check_result "Selected fulfillment option saved" "$FULFILLMENT_ID" "$SELECTED_FULFILLMENT"
echo ""

echo "=================================================="
echo "TEST 3: Payment Tokenization (Delegate Payment)"
echo "=================================================="
echo ""

RESP4=$(curl -s -X POST "$PSP_URL/agentic_commerce/delegate_payment" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-004" \
  -H "Request-Id: test-req-004" \
  -d '{
    "payment_method":{
      "type":"card",
      "card_number_type":"network_token",
      "number":"4242424242424242",
      "exp_month":"12",
      "exp_year":"2027",
      "display_brand":"visa",
      "display_last4":"4242"
    },
    "allowance":{
      "reason":"one_time",
      "max_amount":50000,
      "currency":"usd"
    },
    "risk_signals":[{"type":"fraud_score","score":10,"action":"authorized"}],
    "billing_address":{
      "name":"Test User",
      "line_one":"123 Main St",
      "city":"San Francisco",
      "state":"CA",
      "country":"US",
      "postal_code":"94105"
    }
  }')

TOKEN_ID=$(echo "$RESP4" | jq -r '.id // "ERROR"')
TOKEN_CREATED=$(echo "$RESP4" | jq -r '.created // "ERROR"')
check_result "Payment tokenization returns ID" "true" "$([ "$TOKEN_ID" != "ERROR" ] && [ "$TOKEN_ID" != "null" ] && echo 'true' || echo 'false')"
check_result "Payment tokenization returns created timestamp" "true" "$([ "$TOKEN_CREATED" != "ERROR" ] && [ "$TOKEN_CREATED" != "null" ] && echo 'true' || echo 'false')"
echo "  Token ID: $TOKEN_ID"
echo ""

echo "=================================================="
echo "TEST 4: Order Completion"
echo "=================================================="
echo ""

RESP5=$(curl -s -X POST "$BASE_URL/checkout_sessions/$SESSION_ID2/complete" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-005" \
  -H "Request-Id: test-req-005" \
  -d '{
    "buyer":{"first_name":"John","last_name":"Smith","email":"john@test.com"},
    "payment_data":{"token":"spt_test_123","provider":"stripe"}
  }')

COMPLETED_STATUS=$(echo "$RESP5" | jq -r '.status // "ERROR"')
ORDER_ID=$(echo "$RESP5" | jq -r '.order.id // "ERROR"')
check_result "Completed session has status completed" "completed" "$COMPLETED_STATUS"
check_result "Completed session has order object" "true" "$([ "$ORDER_ID" != "ERROR" ] && [ "$ORDER_ID" != "null" ] && echo 'true' || echo 'false')"
echo "  Order ID: $ORDER_ID"
echo ""

echo "=================================================="
echo "TEST 5: Cancel Session"
echo "=================================================="
echo ""

# Create a new session to cancel
RESP6=$(curl -s -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-006" \
  -H "Request-Id: test-req-006" \
  -d '{"items":[{"id":"1","quantity":1}]}')

SESSION_ID3=$(echo "$RESP6" | jq -r '.id')

RESP7=$(curl -s -X POST "$BASE_URL/checkout_sessions/$SESSION_ID3/cancel" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-007" \
  -H "Request-Id: test-req-007")

CANCEL_STATUS=$(echo "$RESP7" | jq -r '.status // "ERROR"')
check_result "Canceled session has status canceled" "canceled" "$CANCEL_STATUS"
echo ""

echo "=================================================="
echo "TEST 6: Idempotency"
echo "=================================================="
echo ""

# Test 6a: Same key, same payload → same result
echo "→ Test 6a: Same idempotency key with same payload"
RESP8a=$(curl -s -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-dup-001" \
  -H "Request-Id: test-req-008a" \
  -d '{"items":[{"id":"1","quantity":1}]}')

SESSION_ID_8a=$(echo "$RESP8a" | jq -r '.id')

RESP8b=$(curl -s -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-dup-001" \
  -H "Request-Id: test-req-008b" \
  -d '{"items":[{"id":"1","quantity":1}]}')

SESSION_ID_8b=$(echo "$RESP8b" | jq -r '.id')
check_result "Same idempotency key returns same session ID" "$SESSION_ID_8a" "$SESSION_ID_8b"
echo ""

# Test 6b: Same key, different payload → 409 conflict
echo "→ Test 6b: Same idempotency key with different payload"
RESP9=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-dup-001" \
  -H "Request-Id: test-req-009" \
  -d '{"items":[{"id":"2","quantity":3}]}')

HTTP_CODE=$(echo "$RESP9" | tail -n1)
check_result "Different payload with same key returns 409" "409" "$HTTP_CODE"
echo ""

echo "=================================================="
echo "TEST 7: Error Scenarios"
echo "=================================================="
echo ""

# Test 7a: Missing required field
echo "→ Test 7a: Missing required field (empty items)"
RESP10=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-010" \
  -H "Request-Id: test-req-010" \
  -d '{}')

HTTP_CODE_10=$(echo "$RESP10" | tail -n1)
check_result "Missing items field returns 422" "422" "$HTTP_CODE_10"
echo ""

# Test 7b: Out of stock / invalid product
echo "→ Test 7b: Invalid product ID"
RESP11=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-011" \
  -H "Request-Id: test-req-011" \
  -d '{"items":[{"id":"nonexistent_product_99999","quantity":1}]}')

HTTP_CODE_11=$(echo "$RESP11" | tail -n1)
ERROR_CODE_11=$(echo "$RESP11" | head -n-1 | jq -r '.error.code // "none"')
check_result "Invalid product returns error" "true" "$([ "$HTTP_CODE_11" != "201" ] && echo 'true' || echo 'false')"
echo "  Error code: $ERROR_CODE_11"
echo ""

# Test 7c: Payment declined
echo "→ Test 7c: Payment declined with decline_token"
# First create a session ready for payment
RESP12a=$(curl -s -X POST "$BASE_URL/checkout_sessions" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-012a" \
  -H "Request-Id: test-req-012a" \
  -d '{
    "items":[{"id":"1","quantity":1}],
    "fulfillment_address":{
      "name":"Test User",
      "line_one":"123 Main St",
      "city":"San Francisco",
      "state":"CA",
      "country":"US",
      "postal_code":"94105"
    }
  }')

SESSION_ID_12=$(echo "$RESP12a" | jq -r '.id')
FULFILLMENT_ID_12=$(echo "$RESP12a" | jq -r '.fulfillment_options[0].id')

# Update with fulfillment option
curl -s -X POST "$BASE_URL/checkout_sessions/$SESSION_ID_12" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-012b" \
  -H "Request-Id: test-req-012b" \
  -d "{\"fulfillment_option_id\":\"$FULFILLMENT_ID_12\"}" > /dev/null

# Try to complete with decline_token
RESP12c=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/checkout_sessions/$SESSION_ID_12/complete" \
  -H "$AUTH_HEADER" \
  -H "$CONTENT_TYPE" \
  -H "$API_VERSION" \
  -H "Idempotency-Key: test-idem-012c" \
  -H "Request-Id: test-req-012c" \
  -d '{
    "buyer":{"first_name":"John","last_name":"Smith","email":"john@test.com"},
    "payment_data":{"token":"decline_token","provider":"stripe"}
  }')

HTTP_CODE_12=$(echo "$RESP12c" | tail -n1)
ERROR_CODE_12=$(echo "$RESP12c" | head -n-1 | jq -r '.error.code // "none"')
check_result "Payment declined returns error" "true" "$([ "$HTTP_CODE_12" = "402" ] && echo 'true' || echo 'false')"
echo "  HTTP Code: $HTTP_CODE_12"
echo "  Error code: $ERROR_CODE_12"
echo ""

echo "=================================================="
echo "SUMMARY"
echo "=================================================="
echo ""
echo -e "${GREEN}PASSED: $PASS_COUNT${NC}"
echo -e "${RED}FAILED: $FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ Some tests failed. Review the output above.${NC}"
    exit 1
fi