
from __future__ import annotations

import hashlib
from os import PathLike
from pathlib import Path
from typing import BinaryIO


class DocumentHasher:

    def __init__(self, algorithm: str = "sha256", chunk_size: int = 1024 * 1024):
        """Initialize the DocumentHasher with a specific hashing algorithm and chunk size.

        :param algorithm: The hashing algorithm to use (default is 'sha256').
        :param chunk_size: The size of chunks to read from the document (default is 1MB).
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")

        self.algorithm = algorithm
        self.chunk_size = chunk_size

    
    def hash_document(self, document: bytes | bytearray | PathLike | BinaryIO
    ) -> str:
        
        """
        Return the hexadecimal hash of a document's content.
        'document' can be raw bytes (bytes or bytearray) or an open binary stream.
        Streams are read from their current position and are not closed.
        """    

        try:
            digest = hashlib.new(self.algorithm)
        except ValueError as exc:
            raise ValueError(f"unsupported hash algorithm: {self.algorithm}") from exc
        
        if isinstance(document, (bytes, bytearray)):
            digest.update(document)
        elif isinstance(document, (str, Path)):
            with open(document, "rb") as f:
                self._update_digest(digest, f)
        elif hasattr(document, "read"):
            self._update_digest(digest, document)
        else:
            raise TypeError("document must be bytes (bytes or bytearray), a file path (str or Path), or a binary stream")

        return digest.hexdigest()


    def _update_digest(self, digest: any, stream: BinaryIO) -> None:
        """Read a binary stream in chunks and update the digest."""
        while chunk := stream.read(self.chunk_size):
            if not isinstance(chunk, bytes):
                raise TypeError("document stream must be opened in binary mode")
            digest.update(chunk)  
