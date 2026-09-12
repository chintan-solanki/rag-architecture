# End-to-End LLM Observability in FastAPI with OpenTelemetry

## 1. What are we trying to solve?

Suppose we have a RAG application exposed through a FastAPI endpoint:

```text
User
  │
  ▼
POST /query
  │
  ├── Retrieve relevant documents
  │
  ├── Build prompt
  │
  ├── Call LLM
  │
  ├── Post-process response
  │
  ▼
Response
```

At first glance, ordinary application monitoring seems sufficient. We can measure:

* HTTP response time
* HTTP error rate
* CPU/memory usage
* request throughput

But consider a user saying:

> "The answer I got was incorrect."

An ordinary HTTP metric cannot tell us why.

We need to determine:

1. What did the user ask?
2. Which documents were retrieved?
3. How many documents were retrieved?
4. What prompt was ultimately sent to the model?
5. Which model and model parameters were used?
6. How long did retrieval take?
7. How long did the LLM take?
8. How many input/output tokens were consumed?
9. How much did that request cost?
10. Was the generated answer subsequently modified or rejected?
11. Did an evaluation step consider the answer relevant or faithful?

This is the motivation for **LLM observability**.

The important conceptual shift is:

> Don't observe the LLM in isolation. Observe the entire request lifecycle that leads to the LLM's output.

The original article therefore uses OpenTelemetry to represent the request as a structured trace rather than simply writing logs around the LLM call.

# 2. First: what is observability?

Before OpenTelemetry, understand the idea of observability.

Suppose your application behaves incorrectly.

Monitoring might tell you:

```text
Error rate = 3%
p95 latency = 4.2 seconds
```

That's useful, but it doesn't necessarily explain **why**.

Observability is about collecting enough information about a system's execution that you can investigate its internal behavior from the data it produces.

For a conventional application, you might want to know:

```text
HTTP request
    ↓
database query
    ↓
external API
    ↓
business logic
    ↓
response
```

For an LLM application, we want something similar, but the logical operations are different:

```text
HTTP request
    ↓
retrieval
    ↓
prompt construction
    ↓
LLM inference
    ↓
post-processing
    ↓
evaluation
```

This is why traces are particularly useful for LLM applications.

# 3. What is OpenTelemetry?

OpenTelemetry, usually abbreviated as **OTel**, is a vendor-neutral framework for generating and exporting telemetry.

It deals with three major types of telemetry:

```text
Telemetry
├── Traces
├── Metrics
└── Logs
```

This article concentrates primarily on **traces**.

OpenTelemetry does not itself have to be your visualization system.

Think of the architecture as:

```text
Your FastAPI application
        │
        │ OpenTelemetry
        ▼
Telemetry data
        │
        ▼
Observability backend
 ┌──────┼─────────┐
 ▼      ▼         ▼
Jaeger Tempo   Phoenix
```

This separation is important.

Your application generates OpenTelemetry data.

The backend stores and visualizes it.

Therefore, changing from Jaeger to another backend does not require redesigning your application's instrumentation.

# 4. The four concepts you need first

For this tutorial, you only need a few OpenTelemetry concepts.

## Trace

A **trace** represents one end-to-end operation.

For our application:

```text
Trace = one /query request
```

For example:

```text
Trace ID: abc123

User asks:
"What is OpenTelemetry?"
```

Everything that happens while processing that request belongs to the same trace.

---

## Span

A **span** represents one timed operation inside the trace.

For example:

```text
Trace
│
├── retrieval
├── prompt construction
├── LLM call
└── post-processing
```

Each span has a start time and an end time.

Therefore we can determine:

```text
retrieval       = 120 ms
prompt building = 5 ms
LLM             = 1.8 sec
post-processing = 10 ms
```

This is much more useful than simply knowing:

```text
total request = 1.935 sec
```

because we know where the time went.

---

## Attributes

A span can contain key/value metadata.

For example:

```text
llm.model = "gpt-4.1"
llm.temperature = 0.7
rag.top_k = 5
llm.usage.total_tokens = 1842
```

Attributes allow us to filter and analyze traces.

---

## Events

An event is a timestamped occurrence associated with a span.

For example, during streaming:

```text
llm.call
    ├── event: first_token
    ├── event: chunk_received
    ├── event: chunk_received
    └── event: stream_completed
```

You generally don't want to create a separate span for every token or chunk. Events are better suited for milestones inside an operation.

# 5. The most important design decision: what should a trace look like?

For a RAG application, a useful trace is:

```text
http.request
│
├── rag.retrieval
│
├── rag.prompt.build
│
├── llm.call
│
├── llm.postprocess
│
└── llm.eval
```

The last two are optional.

The important principle is:

> Create a span for each meaningful logical stage of the request.

Don't create spans simply because you have functions.

For example, don't do this:

```text
trace
├── function_a
├── function_b
├── function_c
├── function_d
├── function_e
├── function_f
└── function_g
```

That produces implementation-level noise.

Instead:

```text
trace
├── retrieval
├── LLM
└── post-processing
```

The spans should correspond to things an engineer actually wants to reason about.

The original article specifically warns against both extremes:

* one giant span containing the entire workflow
* extremely fine-grained spans such as one span per token

A small number of meaningful spans plus useful attributes is the better design.

# 6. Why RAG makes this particularly useful

Suppose the user receives a bad answer.

There are at least two very different possibilities.

### Problem A: retrieval failed

The retriever returned irrelevant documents.

```text
User question
     │
     ▼
Retriever
     │
     ├── wrong document
     ├── wrong document
     └── irrelevant document
             │
             ▼
            LLM
             │
             ▼
        bad answer
```

The LLM may actually have done exactly what it was asked to do.

### Problem B: retrieval was good, but the LLM failed

```text
User question
     │
     ▼
Retriever
     │
     ├── relevant document
     ├── relevant document
     └── relevant document
             │
             ▼
            LLM
             │
             ▼
        bad answer
```

These require completely different debugging strategies.

Separate spans make this distinction visible.

# 7. A simple FastAPI RAG application

We can build a deliberately simplified application.

First:

```python
from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.trace import Tracer
from typing import List
import asyncio
import hashlib

app = FastAPI()

tracer: Tracer = trace.get_tracer(__name__)
```

`FastAPI()` creates the web application.

`trace.get_tracer(__name__)` gives us an OpenTelemetry tracer.

The tracer is what we use to create spans.

# 8. Simulating retrieval

We'll pretend that a vector database performs the retrieval.

```python
async def retrieve_documents(query: str) -> List[str]:
    await asyncio.sleep(0.05)

    return [
        "FastAPI enables high-performance async APIs.",
        "OpenTelemetry provides vendor-neutral observability.",
        "LLM observability requires tracing prompts and tokens.",
    ]
```

In a real RAG application, this function might instead perform:

```text
query
  ↓
embedding model
  ↓
vector database
  ↓
top-k documents
```

The `sleep()` is only there to simulate latency.

# 9. Building the prompt

Keep prompt construction as a separate logical operation.

```python
def build_prompt(query: str, documents: List[str]) -> str:
    context = "\n".join(documents)

    return f"""
Context:
{context}

Question:
{query}
"""
```

This separation is useful for observability.

If prompt construction becomes expensive because you are processing a huge amount of retrieved context, we can measure that separately from the LLM call.

# 10. Representing an LLM response

For the demonstration, we'll create a small response object:

```python
class LLMResponse:
    def __init__(
        self,
        text: str,
        prompt_tokens: int,
        completion_tokens: int
    ):
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
```

Notice that the original article contains a typo here:

```python
self.completion_tokens = completion_token
```

That should be:

```python
self.completion_tokens = completion_tokens
```

Otherwise the example raises a `NameError`.

Also note that the example's token counting is only an approximation. Real applications should use the token counts reported by the model provider or an appropriate tokenizer.

# 11. Simulating the LLM

Again, we don't actually need an LLM to demonstrate tracing.

```python
async def call_llm(prompt: str) -> LLMResponse:
    await asyncio.sleep(0.2)

    response_text = (
        "FastAPI and OpenTelemetry enable "
        "end-to-end LLM observability."
    )

    # Demonstration only — not real tokenization.
    prompt_tokens = len(prompt.split())
    completion_tokens = len(response_text.split())

    return LLMResponse(
        response_text,
        prompt_tokens,
        completion_tokens,
    )
```

A real implementation would replace this with an OpenAI, Anthropic, local model, or other inference call.

# 12. Post-processing

Keep post-processing separate:

```python
def summarize_response(response: LLMResponse) -> str:
    return response.text
```

Real post-processing might include:

* formatting
* schema validation
* filtering
* safety checks
* citation validation
* truncation
* transforming model output into an API response

# 13. Instrumenting the FastAPI request

Now we combine everything.

```python
@app.post("/query")
async def rag_query(request: Request, query: str):

    with tracer.start_as_current_span("http.request") as http_span:

        http_span.set_attribute("http.method", "POST")
        http_span.set_attribute("http.route", "/query")

        # Retrieval
        with tracer.start_as_current_span(
            "rag.retrieval"
        ) as retrieval_span:

            retrieval_span.set_attribute(
                "rag.top_k",
                5
            )

            retrieval_span.set_attribute(
                "rag.similarity_threshold",
                0.8
            )

            documents = await retrieve_documents(query)

            retrieval_span.set_attribute(
                "rag.documents_returned",
                len(documents)
            )

        # LLM
        with tracer.start_as_current_span(
            "llm.call"
        ) as llm_span:

            llm_span.set_attribute(
                "llm.provider",
                "example"
            )

            llm_span.set_attribute(
                "llm.model",
                "example-llm"
            )

            llm_span.set_attribute(
                "llm.temperature",
                0.7
            )

            llm_span.set_attribute(
                "llm.prompt_template_id",
                "rag_v1"
            )

            prompt = build_prompt(
                query,
                documents
            )

            # Don't put the raw prompt into telemetry.
            prompt_hash = hashlib.sha256(
                prompt.encode()
            ).hexdigest()

            llm_span.set_attribute(
                "llm.prompt_hash",
                prompt_hash
            )

            llm_span.set_attribute(
                "llm.prompt_length",
                len(prompt)
            )

            response = await call_llm(prompt)

            response_hash = hashlib.sha256(
                response.text.encode()
            ).hexdigest()

            llm_span.set_attribute(
                "llm.response_hash",
                response_hash
            )

            llm_span.set_attribute(
                "llm.usage.prompt_tokens",
                response.prompt_tokens
            )

            llm_span.set_attribute(
                "llm.usage.completion_tokens",
                response.completion_tokens
            )

            llm_span.set_attribute(
                "llm.usage.total_tokens",
                response.total_tokens
            )

            estimated_cost = (
                response.total_tokens * 0.000002
            )

            llm_span.set_attribute(
                "llm.cost_estimated_usd",
                estimated_cost
            )

        # Post-processing
        with tracer.start_as_current_span(
            "llm.postprocess"
        ) as post_span:

            summary = summarize_response(response)

            post_span.set_attribute(
                "llm.summary_length",
                len(summary)
            )

    return {
        "summary": summary
    }
```

The important part isn't the FastAPI syntax.

The important part is the **shape of the trace**.

# 14. What does this trace mean?

Conceptually, one request now produces:

```text
Trace
│
└── http.request
     │
     ├── rag.retrieval
     │
     ├── llm.call
     │
     └── llm.postprocess
```

And the individual spans contain metadata.

For example:

```text
rag.retrieval
    duration: 52 ms
    rag.top_k: 5
    rag.similarity_threshold: 0.8
    rag.documents_returned: 3
```

and:

```text
llm.call
    duration: 1.83 sec
    llm.provider: example
    llm.model: example-llm
    llm.temperature: 0.7
    llm.prompt_template_id: rag_v1
    llm.prompt_hash: ...
    llm.prompt_length: ...
    llm.usage.prompt_tokens: 812
    llm.usage.completion_tokens: 94
    llm.usage.total_tokens: 906
    llm.cost_estimated_usd: ...
```

and:

```text
llm.postprocess
    duration: 4 ms
    llm.summary_length: 112
```

Now a trace tells us considerably more than:

```text
POST /query = 1.89 seconds
```

# 15. Why attributes are so important

A span tells us **what happened and how long it took**.

Attributes tell us **under what circumstances it happened**.

Consider:

```text
llm.call
    duration = 2.1 sec
    model = model-A
    temperature = 0.7
    prompt_template = rag_v1
    total_tokens = 3000
```

Suppose we deploy:

```text
model-B
```

and latency suddenly increases.

Because the model is recorded as an attribute, we can compare traces:

```text
model-A → 1.2 sec average
model-B → 2.4 sec average
```

Likewise, we can compare:

```text
rag_v1 → average cost $0.003
rag_v2 → average cost $0.008
```

This is why telemetry should contain **stable, high-value metadata**, rather than arbitrary application data.

# 16. What LLM metadata should we record?

A useful LLM span might contain:

```text
llm.provider
llm.model

llm.temperature
llm.top_p
llm.max_tokens
llm.stream

llm.prompt_template_id
llm.prompt_hash
llm.prompt_length

llm.usage.prompt_tokens
llm.usage.completion_tokens
llm.usage.total_tokens

llm.cost_estimated_usd
```

For example:

```python
with tracer.start_as_current_span(
    "llm.call"
) as llm_span:

    llm_span.set_attribute(
        "llm.provider",
        "example"
    )

    llm_span.set_attribute(
        "llm.model",
        "example-llm"
    )

    llm_span.set_attribute(
        "llm.temperature",
        0.7
    )

    llm_span.set_attribute(
        "llm.top_p",
        0.9
    )

    llm_span.set_attribute(
        "llm.max_tokens",
        512
    )

    llm_span.set_attribute(
        "llm.stream",
        False
    )

    llm_span.set_attribute(
        "llm.prompt_template_id",
        "rag_v1"
    )

    prompt = build_prompt(
        query,
        documents
    )

    prompt_hash = hashlib.sha256(
        prompt.encode()
    ).hexdigest()

    llm_span.set_attribute(
        "llm.prompt_hash",
        prompt_hash
    )

    llm_span.set_attribute(
        "llm.prompt_length",
        len(prompt)
    )
```

The precise attribute names should ideally follow current OpenTelemetry/LLM semantic conventions where applicable rather than inventing arbitrary names.

# 17. Why shouldn't we simply put the prompt into the trace?

This is an important practical consideration.

The prompt may contain:

* personal information
* confidential documents
* proprietary data
* customer information
* authentication information
* sensitive business data

And prompts can be very large.

So telemetry itself becomes sensitive production data.

The article demonstrates hashing:

```python
prompt_hash = hashlib.sha256(
    prompt.encode()
).hexdigest()

llm_span.set_attribute(
    "llm.prompt_hash",
    prompt_hash
)
```

Likewise:

```python
response_hash = hashlib.sha256(
    response.text.encode()
).hexdigest()

llm_span.set_attribute(
    "llm.response_hash",
    response_hash
)
```

The advantage is that we can identify whether two traces used the same content without putting the content itself into the tracing backend.

However, hashing is **not automatically a privacy solution**. If the input has low entropy or predictable values, hashes can sometimes be reversed by guessing. In a real system, you need an explicit decision about what telemetry may contain, who can access it, and how long it is retained.

# 18. Token usage

LLM applications have a cost dimension that ordinary APIs don't usually have.

Suppose two requests have the same latency:

```text
Request A → 500 tokens
Request B → 10,000 tokens
```

They may have radically different costs.

Therefore record:

```text
prompt tokens
completion tokens
total tokens
```

For example:

```python
llm_span.set_attribute(
    "llm.usage.prompt_tokens",
    response.prompt_tokens
)

llm_span.set_attribute(
    "llm.usage.completion_tokens",
    response.completion_tokens
)

llm_span.set_attribute(
    "llm.usage.total_tokens",
    response.total_tokens
)
```

This lets us distinguish:

```text
High cost because:
    prompt is huge
```

from:

```text
High cost because:
    generated response is huge
```

That distinction is particularly useful in RAG systems because retrieved context can unexpectedly make prompts enormous.

# 19. Estimating cost

You can also attach an estimated cost:

```python
estimated_cost = (
    response.total_tokens * 0.000002
)

llm_span.set_attribute(
    "llm.cost_estimated_usd",
    estimated_cost
)
```

The number above is only illustrative.

A real implementation should use:

```text
input_tokens  × input_price
+
output_tokens × output_price
```

because providers commonly price input and output tokens differently.

For example, conceptually:

```python
cost = (
    input_tokens * input_price_per_token
    +
    output_tokens * output_price_per_token
)
```

This allows analysis such as:

```text
Which endpoint costs the most?

Which prompt template costs the most?

Which model costs the most?

Which user workflow produces unusually expensive requests?
```

# 20. Evaluation: observability isn't only about latency

There is an important limitation to ordinary telemetry.

Suppose:

```text
HTTP status = 200
latency = 1.2 sec
tokens = 900
```

Everything looks healthy.

But the answer could still be completely wrong.

Therefore, LLM observability can also include **quality signals**.

For example:

```text
llm.eval.passed = true
llm.eval.relevance_score = 0.91
llm.eval.hallucination_detected = false
llm.eval.refusal_detected = false
```

A simple evaluation could happen synchronously:

```python
with tracer.start_as_current_span(
    "llm.eval"
) as eval_span:

    passed = check_response(response)

    eval_span.set_attribute(
        "llm.eval.passed",
        passed
    )
```

A more sophisticated architecture might use another LLM as an evaluator.

```text
                    ┌── llm.call
                    │
http.request ───────┤
                    │
                    └── llm.eval
```

The evaluator can assess:

* relevance
* faithfulness
* groundedness
* toxicity
* correctness
* hallucination

The important idea is that the evaluation remains associated with the **same trace**, so we can correlate:

```text
prompt version
      +
retrieval configuration
      +
model
      +
latency
      +
cost
      +
quality
```

This is much more powerful than having a separate evaluation dataset with no connection to production execution.

# 21. OpenTelemetry setup conceptually

The article focuses more on instrumentation than on installation details, but conceptually the OpenTelemetry setup consists of four pieces.

### 1. TracerProvider

This manages tracing.

### 2. Resource

Identifies the service.

For example:

```text
service.name = "rag-api"
deployment.environment = "development"
```

### 3. Exporter

Sends telemetry somewhere.

For example:

```text
FastAPI
   │
   ▼
OpenTelemetry SDK
   │
   ▼
OTLP / exporter
   │
   ▼
Jaeger / Tempo / Phoenix
```

### 4. FastAPI instrumentation

OpenTelemetry can automatically instrument incoming HTTP requests.

That means you don't necessarily have to manually create:

```python
http.request
```

for every request.

The HTTP framework instrumentation can create that span for you.

You then create **application-specific spans** such as:

```python
rag.retrieval
llm.call
llm.postprocess
```

This distinction is important:

```text
Auto-instrumentation
    ↓
captures generic infrastructure information

Manual instrumentation
    ↓
captures business/LLM-specific information
```

You generally want both.

# 22. Automatic vs manual instrumentation

Imagine FastAPI automatically creates:

```text
HTTP POST /query
```

That tells you:

```text
request started
request ended
status code
HTTP metadata
```

But it doesn't necessarily know:

```text
this operation is RAG retrieval
this is the prompt version
this is the model
these are the token counts
this is the retrieval top-k
```

Only your application knows that.

Therefore:

```text
Auto instrumentation
       +
Domain-specific manual spans
       =
Useful LLM observability
```

# 23. Async code and context propagation

FastAPI applications are often asynchronous.

For example:

```python
async def rag_query(...):
    documents = await retrieve_documents(...)
    response = await call_llm(...)
```

OpenTelemetry maintains a concept called **context**.

The current span becomes the context in which child spans are created.

So:

```python
with tracer.start_as_current_span("rag.retrieval"):
    ...
```

creates a span associated with the current trace.

Then:

```python
with tracer.start_as_current_span("llm.call"):
    ...
```

creates another span in the same trace when execution proceeds normally within that context.

The result is:

```text
Trace A
│
├── retrieval
└── llm.call
```

rather than two unrelated traces.

Correct context propagation is therefore essential in asynchronous applications.

# 24. Streaming LLM responses

Streaming introduces an interesting problem.

Suppose an LLM produces:

```text
chunk 1
chunk 2
chunk 3
chunk 4
...
```

You generally shouldn't create:

```text
llm.call
├── span chunk 1
├── span chunk 2
├── span chunk 3
...
```

That can generate enormous telemetry volume.

Instead, keep one:

```text
llm.call
```

span and optionally record important events:

```text
llm.call
    │
    ├── event: first_token
    ├── event: chunk_received
    ├── event: chunk_received
    └── event: stream_completed
```

The main span should remain open until the complete stream finishes so its duration represents the actual LLM operation.

# 25. What should not be done?

## Anti-pattern 1: One giant span

Bad:

```text
http.request
    └── everything
```

You can't easily distinguish:

```text
retrieval = 1 sec
LLM = 4 sec
post-processing = 2 sec
```

---

## Anti-pattern 2: Span explosion

Bad:

```text
LLM
├── token 1
├── token 2
├── token 3
├── ...
└── token 5000
```

This creates unnecessary telemetry.

Use attributes/events instead.

---

## Anti-pattern 3: Logging everything

Bad:

```python
logger.info(prompt)
logger.info(response)
```

You may expose sensitive information and lose the correlation between application behavior and distributed request execution.

---

## Anti-pattern 4: Only instrumenting the LLM

This is especially problematic in RAG.

If you only trace:

```text
LLM
```

you cannot tell whether a bad answer came from:

```text
retrieval
prompt construction
LLM
post-processing
```

---

## Anti-pattern 5: Relying entirely on vendor-specific instrumentation

Vendor SDKs can be useful, but your application's observability model should not depend entirely on one provider.

A provider-neutral layer allows you to change:

```text
OpenAI
    ↓
Anthropic
    ↓
local model
```

without redesigning your entire tracing architecture.

# 26. Sampling and telemetry volume

A production system may receive:

```text
10,000 requests/sec
```

Recording every piece of information for every request can become expensive.

Therefore, production systems may use **trace sampling**.

For example:

```text
1,000,000 requests
        │
        ▼
  sampled traces
        │
        ▼
observability backend
```

You can also apply different strategies for:

* errors
* slow requests
* expensive requests
* suspicious quality scores
* normal successful requests

The important point is that observability itself has operational cost.

# 27. Treat telemetry as production data

This is an easily overlooked point.

A trace can contain:

```text
user identifiers
prompt information
model configuration
retrieved documents
cost information
quality information
```

Therefore telemetry needs:

* access control
* retention policies
* appropriate sampling
* privacy considerations
* secure storage

Observability data should not be treated as harmless debug output.

# 28. What do Jaeger, Tempo, and Phoenix actually do?

The instrumentation and backend are separate.

Your code produces:

```text
OpenTelemetry traces
```

Those traces can be consumed by different systems.

### Jaeger

A general-purpose distributed tracing system.

Useful for understanding:

```text
where time was spent
which operations called which
where errors occurred
```

### Grafana Tempo

Another distributed tracing backend, commonly used with the Grafana ecosystem.

### Phoenix

An LLM-focused observability/evaluation platform.

It can make LLM-specific analysis more convenient, such as examining:

* prompts
* generations
* retrieval
* token usage
* quality signals

The key architectural idea is:

```text
Application
     │
OpenTelemetry
     │
     ▼
Backend
```

not:

```text
Application
     │
     └── permanently tied to one observability vendor
```

That portability is one of the major advantages of OpenTelemetry.

# 29. What can we do once traces are available?

Once reliable traces exist, they become useful beyond debugging individual requests.

You can derive aggregate metrics such as:

```text
p50 latency
p95 latency
p99 latency
error rate
average token consumption
average cost
```

You can correlate:

```text
model version
    ×
prompt version
    ×
retrieval configuration
    ×
quality score
```

You can also connect logs to traces using the trace ID.

For example:

```text
Trace ID = abc123

Trace:
    retrieval
    LLM
    postprocess

Logs:
    abc123 - vector DB timeout
    abc123 - fallback model selected
```

This gives you a much more complete picture of a production request.

# 30. The most important mental model

If you are new to both FastAPI and OpenTelemetry, don't start by memorizing APIs.

Start with this mental model:

```text
                    ONE USER REQUEST
                           │
                           ▼
                    ┌─────────────┐
                    │ HTTP request│
                    └──────┬──────┘
                           │
                  ┌────────▼────────┐
                  │    Retrieval    │
                  │                 │
                  │ top_k           │
                  │ threshold       │
                  │ docs returned   │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │ Prompt building │
                  │                 │
                  │ template version│
                  │ prompt size     │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │    LLM call     │
                  │                 │
                  │ provider        │
                  │ model           │
                  │ temperature     │
                  │ tokens          │
                  │ cost            │
                  │ latency         │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │  Post-process   │
                  │                 │
                  │ validation      │
                  │ formatting      │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │   Evaluation    │
                  │                 │
                  │ relevance       │
                  │ faithfulness    │
                  │ safety          │
                  └─────────────────┘
```

OpenTelemetry gives us the mechanism to represent this execution as a **trace**.

Each major box becomes a **span**.

Important information about each box becomes **attributes**.

Important occurrences inside a box become **events**.

The resulting trace can then be sent to Jaeger, Tempo, Phoenix, or another compatible backend.

# 31. The core idea in one example

Imagine that a user reports:

> "The RAG system gave me a completely irrelevant answer."

You open the trace.

You see:

```text
http.request                 1.9 sec
│
├── rag.retrieval            1.2 sec
│      top_k = 5
│      documents_returned = 0
│
├── llm.call                  0.6 sec
│      model = model-A
│      prompt_tokens = 120
│      completion_tokens = 80
│
└── llm.postprocess           0.01 sec
```

Immediately you have a strong hypothesis:

```text
documents_returned = 0
```

The model probably didn't have useful context.

Now consider another trace:

```text
rag.retrieval            50 ms
    documents_returned = 5

llm.call                 2.4 sec
    model = model-B
    prompt_tokens = 8500
    completion_tokens = 3000

llm.postprocess          5 ms
```

Now the problem looks completely different.

Perhaps:

* retrieval returned too much context
* the prompt became unnecessarily large
* the model was slow
* the request was expensive
* the model generated an unusually long answer

This is the real value of LLM observability.

It isn't simply "put traces around your LLM."

It is:

> **Make the important stages and information of an LLM application's execution visible and correlated within one request trace.**

# 32. What you should take away from the article

If you're learning this from scratch, I would reduce the entire article to these eight principles:

### 1. One user request → one trace

The trace gives us the complete execution context.

### 2. One meaningful operation → one span

For RAG:

```text
retrieval
prompt construction
LLM
post-processing
evaluation
```

### 3. Don't confuse infrastructure observability with LLM observability

HTTP latency alone doesn't tell us why an LLM produced an answer.

### 4. Put useful metadata on spans

For example:

```text
model
temperature
prompt version
retrieval parameters
token counts
cost
```

### 5. Separate retrieval problems from generation problems

This is particularly important for RAG.

### 6. Be careful with prompt/response data

Telemetry can contain sensitive information.

### 7. Include quality, not just technical health

A request returning HTTP 200 does not mean the LLM produced a good answer.

### 8. Keep instrumentation independent from the visualization backend

Use OpenTelemetry in the application and choose the backend separately.

That is the architectural idea behind the entire article.
