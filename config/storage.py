from __future__ import annotations

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from vercel.blob import BlobClient
from vercel.blob.errors import BlobNotFoundError


class VercelPrivateBlobStorage(Storage):
    # Django FileField storage backed by a private Vercel Blob store.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = BlobClient()

    def _save(self, name, content):
        if hasattr(content, "seek"):
            try:
                content.seek(0)
            except Exception:
                pass

        if hasattr(content, "chunks"):
            body = b"".join(content.chunks())
        else:
            body = content.read()

        result = self.client.put(
            name,
            body,
            access="private",
            content_type=getattr(content, "content_type", None),
            add_random_suffix=False,
            overwrite=True,
        )
        return result.pathname

    def _open(self, name, mode="rb"):
        result = self.client.get(name, access="private")

        if result is None or result.status_code != 200:
            raise FileNotFoundError(name)

        stream = result.stream
        if stream is None:
            data = b""
        elif hasattr(stream, "read"):
            data = stream.read()
        else:
            data = b"".join(stream)

        return ContentFile(data, name=name)

    def delete(self, name):
        if name:
            self.client.delete(name)

    def exists(self, name):
        if not name:
            return False
        try:
            self.client.head(name)
            return True
        except BlobNotFoundError:
            return False

    def size(self, name):
        return self.client.head(name).size

    def url(self, name):
        return self.client.head(name).url

    def get_modified_time(self, name):
        return self.client.head(name).uploaded_at
