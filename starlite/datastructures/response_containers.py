# pylint: disable=unused-argument
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    AsyncIterator,
    Callable,
    Dict,
    Generic,
    Iterable,
    Iterator,
    List,
    Optional,
    TypeVar,
    Union,
    cast,
)

from pydantic import BaseConfig, FilePath, validator
from pydantic.generics import GenericModel
from typing_extensions import Literal

from starlite.datastructures.background_tasks import BackgroundTask, BackgroundTasks
from starlite.datastructures.cookie import Cookie
from starlite.enums import MediaType
from starlite.exceptions import ImproperlyConfiguredException
from starlite.response import (
    FileResponse,
    RedirectResponse,
    StreamingResponse,
    TemplateResponse,
)
from starlite.response.file import ONE_MEGA_BYTE
from starlite.types.composite import StreamType

if TYPE_CHECKING:
    from starlite.app import Starlite
    from starlite.connection import Request

R = TypeVar("R")


class ResponseContainer(ABC, GenericModel, Generic[R]):
    class Config(BaseConfig):
        arbitrary_types_allowed = True

    background: Optional[Union[BackgroundTask, BackgroundTasks]] = None
    """
        A [BackgroundTask][starlite.datastructures.BackgroundTask] instance or
        [BackgroundTasks][starlite.datastructures.BackgroundTasks] to execute after the response is finished.
        Defaults to None.
    """
    headers: Dict[str, Any] = {}
    """A string/string dictionary of response headers. Header keys are insensitive. Defaults to None."""
    cookies: List[Cookie] = []
    """A list of Cookie instances to be set under the response 'Set-Cookie' header. Defaults to None."""
    media_type: Optional[Union[MediaType, str]] = None
    """If defined, overrides the media type configured in the route decorator"""
    encoding: str = "utf-8"
    """The encoding to be used for the response headers."""

    @abstractmethod
    def to_response(
        self,
        headers: Dict[str, Any],
        media_type: Union["MediaType", str],
        status_code: int,
        app: "Starlite",
        request: "Request",
    ) -> "R":  # pragma: no cover
        """Abstract method that should be implemented by subclasses. Returns a
        Starlette compatible Response instance.

        Args:
            headers: A dictionary of headers.
            media_type: A string or member of the [MediaType][starlite.enums.MediaType] enum.
            status_code: A response status code.
            app: The [Starlite][starlite.app.Starlite] application instance.
            request: A [Request][starlite.connection.request.Request] instance.

        Returns:
            A Response Object
        """
        raise NotImplementedError("not implemented")


class File(ResponseContainer[FileResponse]):
    """Container type for returning File responses."""

    path: FilePath
    """Path to the file to send"""
    filename: Optional[str] = None
    """The filename"""
    stat_result: Optional[os.stat_result] = None
    """File statistics"""
    chunk_size: int = ONE_MEGA_BYTE
    """The size of chunks to use when streaming the file"""
    content_disposition_type: "Literal['attachment', 'inline']" = "attachment"
    """The type of the 'Content-Disposition'. Either 'inline' or 'attachment'."""

    @validator("stat_result", always=True)
    def validate_status_code(  # pylint: disable=no-self-argument
        cls, value: Optional[os.stat_result], values: Dict[str, Any]
    ) -> os.stat_result:
        """Set the stat_result value for the given filepath.

        Args:
            value: An optional result [stat][os.stat] result.
            values: The values dict.

        Returns:
            A stat_result
        """
        return value or Path(cast("str", values.get("path"))).stat()

    def to_response(
        self,
        headers: Dict[str, Any],
        media_type: Optional[Union["MediaType", str]],
        status_code: int,
        app: "Starlite",
        request: "Request",
    ) -> FileResponse:
        """Creates a FileResponse instance.

        Args:
            headers: A dictionary of headers.
            media_type: A string or member of the [MediaType][starlite.enums.MediaType] enum.
            status_code: A response status code.
            app: The [Starlite][starlite.app.Starlite] application instance.
            request: A [Request][starlite.connection.request.Request] instance.

        Returns:
            A FileResponse instance
        """
        return FileResponse(
            background=self.background,
            chunk_size=self.chunk_size,
            content_disposition_type=self.content_disposition_type,
            encoding=self.encoding,
            filename=self.filename,
            headers=headers,
            media_type=media_type,
            path=self.path,
            stat_result=self.stat_result,
            status_code=status_code,
        )


class Redirect(ResponseContainer[RedirectResponse]):
    """Container type for returning Redirect responses."""

    path: str
    """Redirection path"""

    def to_response(  # type: ignore[override]
        self,
        headers: Dict[str, Any],
        # TODO: update the redirect response to support HTML as well.
        #   This argument is currently ignored.
        media_type: Union["MediaType", str],
        status_code: "Literal[301, 302, 303, 307, 308]",
        app: "Starlite",
        request: "Request",
    ) -> RedirectResponse:
        """Creates a RedirectResponse instance.

        Args:
            headers: A dictionary of headers.
            media_type: A string or member of the [MediaType][starlite.enums.MediaType] enum.
            status_code: A response status code.
            app: The [Starlite][starlite.app.Starlite] application instance.
            request: A [Request][starlite.connection.request.Request] instance.

        Returns:
            A RedirectResponse instance
        """
        return RedirectResponse(
            background=self.background,
            encoding=self.encoding,
            headers=headers,
            status_code=status_code,
            url=self.path,
        )


class Stream(ResponseContainer[StreamingResponse]):
    """Container type for returning Stream responses."""

    iterator: Union[StreamType[Union[str, bytes]], Callable[[], StreamType[Union[str, bytes]]]]
    """Iterator, Iterable,Generator or async Iterator, Iterable or Generator returning chunks to stream."""

    @validator("iterator", always=True)
    def validate_iterator(  # pylint: disable=no-self-argument
        cls,
        value: Union[StreamType[Union[str, bytes]], Callable[[], StreamType[Union[str, bytes]]]],
    ) -> StreamType[Union[str, bytes]]:
        """Set the iterator value by ensuring that the return value is
        iterable.

        Args:
            value: An iterable or callable returning an iterable.

        Returns:
            A sync or async iterable.
        """
        return value if isinstance(value, (Iterable, Iterator, AsyncIterable, AsyncIterator)) else value()

    def to_response(
        self,
        headers: Dict[str, Any],
        media_type: Union["MediaType", str],
        status_code: int,
        app: "Starlite",
        request: "Request",
    ) -> StreamingResponse:
        """Creates a StreamingResponse instance.

        Args:
            headers: A dictionary of headers.
            media_type: A string or member of the [MediaType][starlite.enums.MediaType] enum.
            status_code: A response status code.
            app: The [Starlite][starlite.app.Starlite] application instance.
            request: A [Request][starlite.connection.request.Request] instance.

        Returns:
            A StreamingResponse instance
        """

        return StreamingResponse(
            background=self.background,
            content=self.iterator if isinstance(self.iterator, (Iterable, AsyncIterable)) else self.iterator(),
            encoding=self.encoding,
            headers=headers,
            media_type=media_type,
            status_code=status_code,
        )


class Template(ResponseContainer["TemplateResponse"]):
    """Container type for returning Template responses."""

    name: str
    """Path-like name for the template to be rendered, e.g. "index.html"."""
    context: Dict[str, Any] = {}
    """A dictionary of key/value pairs to be passed to the temple engine's render method. Defaults to None."""

    def to_response(
        self,
        headers: Dict[str, Any],
        media_type: Union["MediaType", str],
        status_code: int,
        app: "Starlite",
        request: "Request",
    ) -> "TemplateResponse":
        """Creates a TemplateResponse instance.

        Args:
            headers: A dictionary of headers.
            media_type: A string or member of the [MediaType][starlite.enums.MediaType] enum.
            status_code: A response status code.
            app: The [Starlite][starlite.app.Starlite] application instance.
            request: A [Request][starlite.connection.request.Request] instance.

        Raises:
            [ImproperlyConfiguredException][starlite.exceptions.ImproperlyConfiguredException]: if app.template_engine
                is not configured.

        Returns:
            A TemplateResponse instance
        """
        if not app.template_engine:
            raise ImproperlyConfiguredException("Template engine is not configured")

        return TemplateResponse(
            background=self.background,
            context=self.create_template_context(request=request),
            encoding=self.encoding,
            headers=headers,
            status_code=status_code,
            template_engine=app.template_engine,
            template_name=self.name,
        )

    def create_template_context(self, request: "Request") -> Dict[str, Any]:
        """Creates a context object for the template.

        Args:
            request: A [Request][starlite.connection.request.Request] instance.

        Returns:
        """
        csrf_token = request.scope.get("_csrf_token", "")
        return {
            **self.context,
            "request": request,
            "csrf_input": f'<input type="hidden" name="_csrf_token" value="{csrf_token}" />',
        }
