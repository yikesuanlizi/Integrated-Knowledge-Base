from typing import Optional

from minio import Minio

from app.conf.app_config import config
from app.core.log import logger


class MinioClientManager:
    def __init__(self):
        self._client: Optional[Minio] = None
        self._bucket_name = config.MINIO_BUCKET

    def init(self):
        if self._client is None:
            self._client = Minio(
                config.MINIO_ENDPOINT,
                access_key=config.MINIO_ACCESS_KEY,
                secret_key=config.MINIO_SECRET_KEY,
                secure=False,
            )
            self._ensure_bucket()
            logger.info("MinIO client initialized")

    def _ensure_bucket(self):
        if self._client is None:
            return
        if not self._client.bucket_exists(self._bucket_name):
            self._client.make_bucket(self._bucket_name)
            logger.info(f"MinIO bucket '{self._bucket_name}' created")

    @property
    def client(self) -> Minio:
        if self._client is None:
            self.init()
        return self._client

    def put_object(self, object_name: str, data, length: int):
        return self.client.put_object(
            bucket_name=self._bucket_name,
            object_name=object_name,
            data=data,
            length=length,
        )

    def get_object(self, object_name: str):
        return self.client.get_object(bucket_name=self._bucket_name, object_name=object_name)

    def list_objects(self, prefix: str = "", recursive: bool = False):
        return self.client.list_objects(
            bucket_name=self._bucket_name,
            prefix=prefix,
            recursive=recursive,
        )

    def remove_object(self, object_name: str):
        return self.client.remove_object(bucket_name=self._bucket_name, object_name=object_name)

    def remove_objects(self, objects):
        return self.client.remove_objects(bucket_name=self._bucket_name, delete_object_list=objects)

    def clear_bucket(self):
        objects = list(self.list_objects(recursive=True))
        if not objects:
            return
        self.remove_objects(objects)


minio_client_manager = MinioClientManager()


def get_minio_client():
    return minio_client_manager.client
