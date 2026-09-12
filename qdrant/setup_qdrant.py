import sys
import time

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    VectorParams,
    SparseVectorParams,
    Distance,
)

QDRANT_HOST, QDRANT_PORT = "qdrant", 6333
DENSE_COLLECTION_NAME = "test_collection"
HYBRID_COLLECTION_NAME = "hybrid_collection"
VECTOR_SIZE = 384
DISTANCE = "Cosine"

MAX_WAIT_SECONDS = 60
RETRY_INTERVAL_SECONDS = 2

def create_collection_if_missing(client: QdrantClient) -> None:
    if client.collection_exists(DENSE_COLLECTION_NAME):
        print(f"Collection '{DENSE_COLLECTION_NAME}' already exists. We are good!")
    else:
        print(f"Creating collection '{DENSE_COLLECTION_NAME}'...")

        client.create_collection(
            collection_name=DENSE_COLLECTION_NAME,
            vectors_config={
                "size": VECTOR_SIZE,
                "distance": DISTANCE,
            },
        )

    if client.collection_exists(HYBRID_COLLECTION_NAME):
        print(f"Collection '{HYBRID_COLLECTION_NAME}' already exists. We are good!")
    else:
        client.create_collection(
            collection_name=HYBRID_COLLECTION_NAME,
            vectors_config={
                "text-dense": VectorParams(
                    size=VECTOR_SIZE,
                    distance=DISTANCE,
                )
            },
            sparse_vectors_config={
                "text-sparse-new": SparseVectorParams()
            }
        )
        print(f"Collection '{HYBRID_COLLECTION_NAME}' created.")


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