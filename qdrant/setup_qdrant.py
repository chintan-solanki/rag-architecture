import sys
import time

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse


QDRANT_HOST, QDRANT_PORT = "qdrant", 6333
COLLECTION_NAME = "test_collection2"
VECTOR_SIZE = 384
DISTANCE = "Cosine"

MAX_WAIT_SECONDS = 60
RETRY_INTERVAL_SECONDS = 2

def create_collection_if_missing(client: QdrantClient) -> None:
    if client.collection_exists(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' already exists. We are good!")
        return

    print(f"Creating collection '{COLLECTION_NAME}'...")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "size": VECTOR_SIZE,
            "distance": DISTANCE,
        },
    )

    print(f"Collection '{COLLECTION_NAME}' created.")


def main() -> int:
    deadline = time.monotonic() + MAX_WAIT_SECONDS

    client = QdrantClient(
        host=QDRANT_HOST,
        port=QDRANT_PORT,
    )

    while time.monotonic() < deadline:
        try:
            print(
                f"Connecting to Qdrant at "
                f"{QDRANT_HOST}:{QDRANT_PORT}..."
            )

            # Actually perform an API call. Merely constructing
            # QdrantClient does not establish a connection.
            client.get_collections()

            print("Qdrant is ready.")

            create_collection_if_missing(client)
            return 0

        except Exception as exc:
            remaining = max(0, int(deadline - time.monotonic()))

            print(
                f"Qdrant is not ready yet: {exc}. "
                f"Retrying ({remaining}s remaining)..."
            )

            time.sleep(RETRY_INTERVAL_SECONDS)

    print(
        f"ERROR: Qdrant did not become ready within "
        f"{MAX_WAIT_SECONDS} seconds.",
        file=sys.stderr,
    )

    return 1


if __name__ == "__main__":
    sys.exit(main())