# Malaika Fayyaz - BSCS23013

## PDC Assignment 2: Building Resilient Distributed Systems

### Introduction

This repository implements **Problem 1: Synchronization** by fixing the Lost Update anomaly with optimistic locking. It also explains the design approach for Problems 2 and 3.

---

## Problem 1: Synchronization (Lost Update)

When two users edit the same challenge at the same time, the application could silently overwrite one user's changes.

### Implemented solution

- Added `version` field to `Challenge` records.
- Update requests must include the client's last-read version.
- The server only applies the update if the submitted version matches the current version.
- On mismatch, the server returns `409 Conflict` with the current version.
- This ensures no silent lost updates and enables client retry.

### Implementation details

- `backend/src/database/models.py`
  - Added `version = Column(Integer, default=1, nullable=False)`
- `backend/src/database/db.py`
  - Added `update_challenge_with_optimistic_locking()`
- `backend/src/routes/challenge.py`
  - Added `PATCH /api/challenge/{challenge_id}` with version validation
- `backend/src/app.py`
  - Added middleware to inject `X-Student-ID: BSCS23013`

---

## Problem 2: Coordination (Webhook Reliability)

If Clerk sends a cancellation webhook and it is dropped by a network failure, the backend can remain out of sync and the user stays premium.

### Proposed design

- Persist incoming webhook events with an `event_id`.
- Acknowledge receipt only after storing the event.
- Process events asynchronously.
- Retry on transient failures.
- Send permanently failed events to a dead-letter queue.
- Use idempotency to ignore duplicate deliveries.

---

## Problem 3: Fault Tolerance (LLM Blocking)

The external LLM API can time out or hang, blocking FastAPI threads and making the app unresponsive.

### Proposed design

- Use async calls with a short timeout.
- Wrap the LLM integration in a circuit breaker.
- On repeated failures, open the circuit and use a fallback response.
- This keeps the application responsive even when the LLM is unavailable.

---

## Running the project

### Recommended command

```bash
python test_optimistic_locking.py
```
This is the main demo for the implemented fix.

### Other useful commands

```bash
python test_integration.py
```
- `test_integration.py` validates concurrent update behavior and conflict handling.

---

## Notes

- Only Problem 1 is implemented in code.
- Problems 2 and 3 are described as design improvements.
- `X-Student-ID: BSCS23013` is included on every response via middleware.


### ✓ CAP Theorem Trade-offs
- Chose: **Availability + Partition Tolerance (AP)**
- Sacrificed: Strong Consistency
- Gained: Eventual Consistency + High Availability

---

## File Structure

```
SecureAIApp/
├── backend/
│   ├── pyproject.toml
│   ├── server.py
│   ├── src/
│   │   ├── __init__.py
│   │   ├── app.py                    [MODIFIED: StudentIDMiddleware]
│   │   ├── ai_generator.py
│   │   ├── utils.py
│   │   ├── database/
│   │   │   ├── db.py                 [MODIFIED: Added optimistic locking function]
│   │   │   └── models.py             [MODIFIED: Added version column]
│   │   └── routes/
│   │       ├── challenge.py          [MODIFIED: Added PATCH endpoint]
│   │       └── webhooks.py
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── src/
│   │   └── ... (frontend code)
│   └── ... (config files)
├── ANALYSIS_AND_DESIGN.md             [NEW: Part 1 & 2 Analysis]
├── test_optimistic_locking.py         [NEW: Unit tests]
├── test_integration.py                [NEW: Integration tests]
└── demo_script.py                     [NEW: Demonstration script]
```

---

## Changes Made

### 1. Modified `backend/src/database/models.py`
- Added `version` column to Challenge model for optimistic locking

### 2. Modified `backend/src/database/db.py`
- Added `update_challenge_with_optimistic_locking()` function
- Implements conflict detection logic

### 3. Modified `backend/src/routes/challenge.py`
- Added `UpdateChallengeRequest` Pydantic model
- Added `challenge_to_dict()` helper to include version in responses
- Added `PATCH /api/challenge/{challenge_id}` endpoint with version check
- Updated `GET /generate-challenge` to return version
- Updated `GET /my-history` to include version in history

### 4. Modified `backend/src/app.py`
- Added `StudentIDMiddleware` class
- Middleware adds `X-Student-ID: BSCS23013` header to all responses

### 5. New Files Created
- `ANALYSIS_AND_DESIGN.md` - Part 1 & 2 written analysis
- `test_optimistic_locking.py` - Unit tests demonstrating the fix
- `test_integration.py` - Integration tests with mock store
- `demo_script.py` - Interactive demonstration script

---

## How Optimistic Locking Works

### 1. Read Phase
Client fetches resource and gets current version:
```
Challenge {id: 1, title: "...", version: 5}
```

### 2. Modify Phase
Client modifies data locally (version doesn't change):
```
Challenge {id: 1, title: "NEW TITLE", version: 5}
```

### 3. Write Phase
Client submits update WITH the version number they read:
```
PATCH /api/challenge/1
{
  "title": "NEW TITLE",
  "version": 5
}
```

### 4. Conflict Detection
Server checks: `WHERE id=1 AND version=5`
- ✓ If match found: Update succeeds, version incremented
- ❌ If no match: Conflict detected, 409 response

### 5. Retry Loop
If conflict (409):
- Client reads current version
- Retries with new version
- Update succeeds on retry

---

## Example Usage

### Concurrent Updates Without Conflict

```
User A (thread 1):          User B (thread 2):
1. GET challenge v=1
2. Modify title
3. PATCH version=1          1. GET challenge v=1
                            2. Modify explanation
                            3. PATCH version=1 → 409 CONFLICT
4. ✓ Success v=2
                            4. GET challenge v=2
                            5. PATCH version=2
                            6. ✓ Success v=3

Final result:
- Title: Updated by User A ✓
- Explanation: Updated by User B ✓
- No data lost ✓
```

---

## Testing Scenarios

### Scenario 1: Basic Update
- Single user updates challenge
- Version increments correctly
- Response includes new version

### Scenario 2: Concurrent Read, Sequential Write
- Two users read same version
- First user updates → success, v2
- Second user attempts update with v1 → conflict 409
- Second user refreshes and retries → success, v3

### Scenario 3: Three-Way Concurrent Updates
- Three users read same version
- All three attempt updates
- First succeeds, other two get 409
- Both retry with new version
- All three changes eventually applied

---

## CAP Theorem Analysis

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Consistency** | Eventual | Conflicts detected post-write, not prevented pre-write |
| **Availability** | Yes | No blocking reads/writes, conflicts trigger retry |
| **Partition Tolerance** | Yes | Clients continue operating independently |

**Trade-off:** We sacrifice **strong consistency** for **high availability**. This is appropriate for a collaborative editing application where it's better to temporarily allow conflicts than to block all operations.

