"""External OA and event integration boundary."""

from .java_facade import (
    JavaFacadeBusinessError,
    JavaFacadeConnectionError,
    JavaFacadeHttpError,
    JavaFacadeJsonDecodeError,
    JavaFacadeResponseTypeError,
    java_get,
    java_get_list,
    java_post,
    java_post_list,
)
from .oa_client import JavaFacadeClient

__all__ = [
    "JavaFacadeBusinessError", "JavaFacadeClient", "JavaFacadeConnectionError", "JavaFacadeHttpError",
    "JavaFacadeJsonDecodeError", "JavaFacadeResponseTypeError",
    "java_get", "java_get_list", "java_post", "java_post_list",
]
