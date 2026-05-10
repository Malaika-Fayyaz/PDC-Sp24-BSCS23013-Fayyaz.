# PDC Assignment 2: Building Resilient Distributed Systems
## Problem 1 - Synchronization (Lost Update Anomaly)

**Student:** Malaika Fayyaz  
**Student ID:** BSCS23013  
**Date:** May 4, 2026

---

## Part 1: Analyze the Mess (Root Cause Analysis)

### Problem 1: Lost Update Anomaly

#### Scenario
Two users attempt to edit the same coding challenge simultaneously. User A fetches a challenge and modifies the title. User B fetches the same challenge and modifies the explanation. Both users submit their updates within milliseconds of each other. The system silently accepts both updates, but one user's changes are lost because they both read the same original version and wrote back independently.

#### Root Cause Analysis

**1. Database Level - No Versioning**

Looking at the current schema in `backend/src/database/models.py`:

```python
class Challenge(Base):
    __tablename__ = 'challenges'
    
    id = Column(Integer, primary_key=True)
    difficulty = Column(String, nullable=False)
    date_created = Column(DateTime, default=datetime.now)
    created_by = Column(String, nullable=False)
    title = Column(String, nullable=False)
    options = Column(String, nullable=False)
    correct_answer_id = Column(Integer, nullable=False)
    explanation = Column(String, nullable=False)
```

**Problem:** There is no `version` or `timestamp` column to track mutations. The system has no mechanism to detect if the data has been modified since the client last read it.

**2. API Level - Read-Modify-Write Without Concurrency Control**

In `backend/src/routes/challenge.py`, there is no endpoint for updating a challenge. However, if there were one, the typical pattern would be:

```
1. Client A reads Challenge #5 (v=1) → {title: "Q1", explanation: "E1"}
2. Client B reads Challenge #5 (v=1) → {title: "Q1", explanation: "E1"}
3. Client A modifies title → {title: "Q1_MODIFIED", explanation: "E1"}
4. Client B modifies explanation → {title: "Q1", explanation: "E1_MODIFIED"}
5. Client A submits update (no version check) → DB now has {title: "Q1_MODIFIED", explanation: "E1"}
6. Client B submits update (no version check) → DB now has {title: "Q1", explanation: "E1_MODIFIED"}
```

Result: Client A's title modification is lost.

**3. Transaction Isolation - Read Committed (Default)**

SQLAlchemy with SQLite uses Read Committed isolation by default, which is vulnerable to non-repeatable reads and phantom reads in concurrent scenarios. Two read operations can see different versions of the same row.

#### Manifestation in Current Code

1. **No optimistic locking**: The database doesn't track which version of a record the client is working with
2. **No pessimistic locking**: The system doesn't prevent concurrent reads of the same record
3. **No conflict detection**: When writes happen, there's no validation that the underlying data hasn't changed
4. **Silent overwrites**: The second write completely overwrites the first, with no warning or rollback

---

## Part 2: Design a Better System

### Solution: Optimistic Locking with Version Control

Optimistic locking allows concurrent reads but detects conflicts at write time. Every record has a version number that increments on each update. When a client attempts to update, it must provide the version it read. If the current version differs, a conflict is detected.

#### Architecture

**1. Database Schema Enhancement**

Add a `version` column to the `Challenge` model:

```python
class Challenge(Base):
    __tablename__ = 'challenges'
    
    id = Column(Integer, primary_key=True)
    difficulty = Column(String, nullable=False)
    date_created = Column(DateTime, default=datetime.now)
    created_by = Column(String, nullable=False)
    title = Column(String, nullable=False)
    options = Column(String, nullable=False)
    correct_answer_id = Column(Integer, nullable=False)
    explanation = Column(String, nullable=False)
    version = Column(Integer, default=1, nullable=False)  # NEW: Version tracking
```

**2. Update Mechanism with Version Check**

When updating a challenge:
```
UPDATE challenges 
SET title = ?, explanation = ?, version = version + 1
WHERE id = ? AND version = ?
```

If no rows are affected, a conflict occurred.

**3. API Contract**

**GET Response:**
```json
{
  "id": 1,
  "title": "Python Basics",
  "difficulty": "easy",
  "version": 5,
  "explanation": "..."
}
```

**PATCH Request:**
```json
{
  "title": "Updated Title",
  "version": 5
}
```

**PATCH Response (Success):**
```json
{
  "id": 1,
  "title": "Updated Title",
  "version": 6
}
```

**PATCH Response (Conflict - HTTP 409):**
```json
{
  "error": "Conflict",
  "message": "Resource was modified. Current version is 6, you submitted version 5",
  "current_version": 6
}
```

#### UML Sequence Diagram

```
User A                          Server                          Database                          User B
 |                               |                               |                                 |
 |----GET /challenge/1---------->|                               |                                 |
 |                               |----SELECT * FROM challenges---|                                 |
 |                               |<-----{id:1, v:5, title:Q1}---|                                 |
 |<--{id:1, v:5, title:Q1}-------|                               |                                 |
 |                               |                               |                                 |----GET /challenge/1------->|
 |                               |                               |                                 |
 |                               |                               |----SELECT * FROM challenges----|
 |                               |                               |<-----{id:1, v:5, title:Q1}---|
 | Modifies title to "Q1_A"      |                               | |<---{id:1, v:5, title:Q1}---|
 | (still has v:5)               |                               |                                 |
 |                               |                               |                    Modifies title to "Q1_B"
 |                               |                               |                    (still has v:5)
 |                               |                               |                                 |
 |----PATCH /challenge/1-------->|                               |                                 |
 | {title:"Q1_A", version:5}     |                               |                                 |
 |                               |----UPDATE WHERE id=1 & v=5----|                                 |
 |                               |    SET title="Q1_A", v=6      |                                 |
 |                               |<-------1 row updated----------|                                 |
 |<--{id:1, v:6, title:Q1_A}----|                               |                                 |
 |                               |                               |                                 |----PATCH /challenge/1----->|
 |                               |                               |          {title:"Q1_B", version:5}
 |                               |                               |                                 |
 |                               |----UPDATE WHERE id=1 & v=5----|                                 |
 |                               |    SET title="Q1_B", v=6      |                                 |
 |                               |<-------0 rows updated---------|                                 |
 |                               |                               |                                 |
 |                               |<--409 Conflict Error----------|                                 |
 |                               | {error: "version mismatch",   |                                 |
 |                               |  current_version: 6}          |                                 |
 |                               |                               |                                 |<--409 Conflict Error------|
 |                               |                               |                                 | {error: "version mismatch"}
 |                               |                               |                                 |
 |                               |                               |                                 | Retries: GET /challenge/1
 |                               |                               |                                 |
 |                               |----SELECT * FROM challenges---|                                 |
 |                               |<-----{id:1, v:6, title:Q1_A}-|                                 |
 |                               |                               | <---{id:1, v:6, title:Q1_A}---|
 |                               |                               |                                 |
 |                               |                               |                      Merges or retries
```

#### CAP Theorem Trade-offs

The optimistic locking solution makes the following trade-offs:

| Characteristic | Trade-off | Justification |
|---|---|---|
| **Consistency** | Sacrifice immediate consistency for eventual correctness | Conflicts are detected at write time, not preventing reads. Multiple clients may briefly work with stale data, but conflicts are reliably detected. |
| **Availability** | High availability maintained | The system doesn't block reads or writes. Conflicts trigger a retry mechanism, which is still available. |
| **Latency** | Minimal latency impact | No additional DB locks or blocking operations. Conflict resolution is delegated to the client via retries. |
| **Network Partition Tolerance** | Resilient to partial failures | Clients can continue reading/writing independently. On reconnection, version conflicts naturally resolve. |

**Trade-off Summary:**
- We accept **eventual consistency** (conflicts detected post-write) instead of strong consistency (prevented at write time)
- We maintain **high availability** by allowing concurrent readers
- We improve **latency** by avoiding pessimistic locks
- We gain **fault tolerance** during network partitions

This is an **AP system** (Availability + Partition tolerance) per CAP theorem, sacrificing strong Consistency in favor of operational resilience.

#### Implementation Strategy

1. Add `version` column to Challenge model
2. Create database migration to add the column
3. Modify/create UPDATE endpoint to include version check
4. Return version in all GET responses
5. Include middleware for X-Student-ID header
6. Write test cases simulating concurrent updates
7. Provide client-side retry logic

---

## Problem 2 - Coordination (Webhook Reliability)

### Scenario
A Clerk webhook notifies the backend when a user cancels premium access. If the webhook is dropped by a network blip or the backend temporarily fails, the user remains premium and the systems diverge.

### Root Cause Analysis

**1. Delivery Assumption**
The current webhook flow assumes Clerk will deliver the event exactly once and that the backend will process it immediately. In reality, webhooks are at-best-once and can be delayed, duplicated, or dropped.

**2. No Durability or Replay**
There is no persistent store for incoming webhook events. If the handler fails after acknowledgment, the event is lost forever.

**3. No Idempotency**
If Clerk retries the same webhook event, the backend may process it twice unless the event is explicitly deduplicated.

**4. No Asynchronous Processing**
The webhook handler likely performs the state update synchronously. That means a transient failure can cause lost or incomplete state changes.

### Solution: Durable, Idempotent, Retryable Webhook Processing

Implement a webhook pipeline with these elements:

1. **Persist incoming events** in a `webhook_events` table with `event_id`, `type`, `payload`, `status`, and timestamps.
2. **Acknowledge receipt immediately** to Clerk once the event is stored.
3. **Enqueue processing** for background workers.
4. **Process events asynchronously** and mark them as completed.
5. **Retry failures** with exponential backoff.
6. **Move permanent failures** to a dead-letter queue for manual review.
7. **Use idempotency keys** so repeated deliveries of the same event are ignored.

### Proposed Flow

```
Clerk → Webhook API → DB store → Queue → Worker → Business logic → DB update
              |                                         |
              |                                         └─ Success ✅
              |                                         └─ Retry / DLQ ❌
              |
              └─ ACK (after store)
```

### Key Design Elements

* **Event persistence**: Store `event_id` and raw payload before processing.
* **Idempotency**: Reject duplicate `event_id` entries, or mark them as already processed.
* **Retry policy**: Retry transient failures automatically, e.g. 3-5 times.
* **DLQ**: Preserve failed events for later inspection if retries fail.
* **Audit trail**: Record when each webhook arrived, processed, and whether it succeeded.

### Example Event Table Schema

```python
class WebhookEvent(Base):
    __tablename__ = 'webhook_events'
    id = Column(Integer, primary_key=True)
    event_id = Column(String, unique=True, nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(String, nullable=False)
    status = Column(String, nullable=False, default='pending')
    attempts = Column(Integer, nullable=False, default=0)
    last_attempted_at = Column(DateTime)
    processed_at = Column(DateTime)
```

### Diagram

```
Clerk → Webhook Receiver → Persist Event → Queue → Worker → Apply Change
                        ↘---------------------↗
                                 Retry
```

### CAP Trade-offs

| Characteristic | Trade-off | Justification |
|---|---|---|
| Consistency | Eventual consistency | Webhook updates are not applied immediately in the business state, but they are durable and replayable.
| Availability | High availability | The webhook receiver acknowledges quickly and does not block on processing.
| Latency | Slightly higher end-to-end latency | Processing may happen asynchronously, but retries prevent silent loss.

This is a **PR system**: it prioritizes **Partition tolerance and Availability**, while accepting eventual consistency for webhook coordination.

---

## Problem 3 - Fault Tolerance (LLM API Blocking)

### Scenario
The app calls an external LLM API to generate challenges. If the LLM takes 60 seconds to timeout, FastAPI waits synchronously, blocking worker threads and causing the whole application to hang for all users.

### Root Cause Analysis

**1. Synchronous dependence on remote API**
The backend blocks while waiting for the LLM response, tying up a request thread for the entire timeout duration.

**2. No timeout or circuit breaker**
There is no protective timeout or failure-handling layer around the external API call.

**3. No fallback mode**
When the LLM fails, there is no alternative response or cached result, so the request either hangs or returns an error.

**4. Single point of failure**
The external LLM becomes a critical dependency. If it is slow or unavailable, the entire service degrades.

### Solution: Async, Timeouts, Circuit Breaker, Fallback

Use a fault-tolerant integration pattern for the LLM API:

1. **Async HTTP client** (`httpx`, `aiohttp`) to avoid blocking FastAPI worker threads.
2. **Short request timeout** (2-3 seconds) so the app fails fast.
3. **Circuit breaker** to open when failures exceed a threshold.
4. **Fallback behavior** when the circuit is open or the API fails.
5. **Retries with backoff** for transient errors.

### Proposed Flow

```
Client → FastAPI → Circuit Breaker → Async LLM call
                     |
                     ├─ Success → return result
                     ├─ Failure → count failure
                     └─ Open → fallback / cache
```

### Circuit Breaker States

* **Closed**: normal operation
* **Open**: external service failing, block calls for a short window
* **Half-open**: test a limited number of calls before closing again

### Fallback Strategies

* Return a cached challenge or template response
* Return a clear error message like `LLM temporarily unavailable`
* Use a simpler local generation path if available

### Example Pseudocode

```python
async def generate_challenge(difficulty):
    if circuit_breaker.is_open():
        return cached_or_fallback_result()

    try:
        with timeout(3):
            response = await llm_client.generate(...)
            circuit_breaker.record_success()
            return response
    except Exception as exc:
        circuit_breaker.record_failure()
        if circuit_breaker.is_open():
            return cached_or_fallback_result()
        raise
```

### CAP Trade-offs

| Characteristic | Trade-off | Justification |
|---|---|---|
| Availability | Increased | The app remains responsive even if the LLM is down.
| Consistency | Lowered in fallback responses | The returned output may be less accurate or stale.
| Latency | Reduced | Fast failure avoids a 60-second hang.

This pattern chooses **Availability over strong consistency** and prevents the LLM from becoming a system-wide outage.

---

## Combined Design Summary

| Problem | Proposed Fix | Key Benefit |
|---|---|---|
| Synchronization | Optimistic locking with version control | Prevents silent lost updates |
| Coordination | Durable webhook pipeline with idempotency and retries | Prevents dropped subscription events |
| Fault tolerance | Circuit breaker, async calls, fallback | Prevents LLM outages from hanging the app |

### Final Notes

For StudySync, the right architecture is:

* Problem 1: keep the user-facing data operations consistent with versioned writes
* Problem 2: make external event delivery reliable and replayable
* Problem 3: isolate the LLM dependency and fail fast with graceful fallback

Together, these changes make the system robust for a real production launch.

