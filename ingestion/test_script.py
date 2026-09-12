import asyncio
import contextvars

# 1. Declare the variable at the module level
request_id_var = contextvars.ContextVar("request_id", default="No ID")

async def sleep_fn(delay):
    await asyncio.sleep(delay)
    print(f'inside sleep function: {request_id_var.get()}')


async def process_request(name, req_id, delay):
    # 2. Set the context-local value for this specific async flow
    token = request_id_var.set(req_id)
    
    # Simulate an async operation (yielding control)
    await sleep_fn(delay)
    
    # 3. Retrieve the value (it remains isolated to this task!)
    print(f"Task {name} has Request ID: {request_id_var.get()}")
    
    # 4. Clean up / Reset if necessary
    request_id_var.reset(token)

async def main():
    # Run two tasks concurrently
    await asyncio.gather(
        process_request("A", "ABC-123", 2),
        process_request("B", "XYZ-789", 1)
    )

def sync_fun():
    token = request_id_var.set('sync_req')
    print(request_id_var.get())
    request_id_var.reset(token)

sync_fun()
asyncio.run(main())


