"""Минимальный HTTP-клиент на стандартной библиотеке.

Почему без requests: пользователю на Windows не нужно ничего ставить, кроме
самого Python. Клиент умеет multipart-загрузку файлов, повторные попытки при
429/5xx и сетевых сбоях, разбор JSON и понятные ошибки.
"""

from __future__ import annotations

import json as jsonlib
import mimetypes
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
USER_AGENT = "social-publisher/0.1 (image_gallery; +https://github.com/vrabote/image_gallery)"
MAX_BODY = 512 * 1024 * 1024


class HTTPError(RuntimeError):
    """Сетевой сбой или ответ, который адаптер не смог использовать."""

    def __init__(self, message: str, *, status: int | None = None, body: str = "", url: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body
        self.url = url


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str]
    url: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self) -> Any:
        try:
            return jsonlib.loads(self.body.decode("utf-8") or "null")
        except (UnicodeDecodeError, jsonlib.JSONDecodeError) as exc:
            snippet = self.text[:400].replace("\n", " ")
            raise HTTPError(
                f"Ответ не является JSON ({self.status}): {snippet}",
                status=self.status,
                body=self.text,
                url=self.url,
            ) from exc

    def header(self, name: str, default: str = "") -> str:
        return self.headers.get(name.lower(), default)


# ---------------------------------------------------------------------------
# multipart
# ---------------------------------------------------------------------------

FileSpec = tuple  # (field, path|bytes, filename?, content_type?)


def _normalise_files(files: Sequence[FileSpec]) -> list[tuple[str, Any, str | None, str | None]]:
    normalised = []
    for spec in files:
        if len(spec) == 2:
            field, source = spec
            normalised.append((field, source, None, None))
        elif len(spec) == 3:
            field, source, filename = spec
            normalised.append((field, source, filename, None))
        else:
            field, source, filename, content_type = spec
            normalised.append((field, source, filename, content_type))
    return normalised


def encode_multipart(
    fields: Mapping[str, Any] | None,
    files: Sequence[FileSpec] | None,
    boundary: str | None = None,
) -> tuple[str, bytes]:
    """Собрать тело multipart/form-data. Возвращает (content_type, body)."""
    boundary = boundary or f"----socialpublisher{os.urandom(10).hex()}"
    out = bytearray()
    for name, value in (fields or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = "1" if value else "0"
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += str(value).encode("utf-8") + b"\r\n"
    for field, source, filename, content_type in _normalise_files(files or []):
        if isinstance(source, (str, Path)):
            path = Path(source)
            data = path.read_bytes()
            filename = filename or path.name
        else:
            data = source
            filename = filename or field
        content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode()
        out += f"Content-Type: {content_type}\r\n\r\n".encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return f"multipart/form-data; boundary={boundary}", bytes(out)


# ---------------------------------------------------------------------------
# клиент
# ---------------------------------------------------------------------------


class HTTPClient:
    def __init__(
        self,
        timeout: float = 120,
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] | None = None,
        max_body: int = MAX_BODY,
    ):
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.sleep = sleep
        self.log = log or (lambda _msg: None)
        self.max_body = max_body

    # -- публичные методы ---------------------------------------------------
    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Response:
        return self.request("DELETE", url, **kwargs)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        files: Sequence[FileSpec] | None = None,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> Response:
        if params:
            encoded = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}, doseq=True
            )
            if encoded:
                url = f"{url}{'&' if '?' in url else '?'}{encoded}"

        body: bytes | None = None
        request_headers: dict[str, str] = {"User-Agent": USER_AGENT, "Accept": "application/json, */*"}

        if json is not None:
            body = jsonlib.dumps(json, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json; charset=utf-8"
        elif files is not None:
            content_type, body = encode_multipart(data, files)
            request_headers["Content-Type"] = content_type
        elif data is not None:
            if isinstance(data, Mapping):
                body = urllib.parse.urlencode(
                    {k: v for k, v in data.items() if v is not None}, doseq=True
                ).encode("utf-8")
                request_headers["Content-Type"] = "application/x-www-form-urlencoded"
            elif isinstance(data, bytes):
                body = data
            elif isinstance(data, (str, Path)):
                body = Path(data).read_bytes()
            else:  # файловый объект
                body = data.read()
        request_headers.update(headers or {})

        attempts = (self.retries if retries is None else max(0, retries)) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=body, headers=request_headers, method=method.upper())
            try:
                with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                    payload = response.read(self.max_body)
                    return Response(
                        response.status,
                        payload,
                        {k.lower(): v for k, v in response.headers.items()},
                        response.geturl(),
                    )
            except urllib.error.HTTPError as exc:
                payload = b""
                try:
                    payload = exc.read(self.max_body) if exc.fp else b""
                except Exception:  # pragma: no cover - защита от странных ответов
                    payload = b""
                result = Response(
                    exc.code,
                    payload,
                    {k.lower(): v for k, v in (exc.headers or {}).items()},
                    url,
                )
                if exc.code in RETRY_STATUSES and attempt < attempts - 1:
                    self._wait(attempt, result)
                    continue
                return result
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    self._wait(attempt, None)
                    continue
                raise HTTPError(f"Сеть недоступна: {method} {url}: {exc}", url=url) from exc
        raise HTTPError(f"Запрос не удался: {method} {url}: {last_error}", url=url)

    # -- потоковая отправка файла (resumable upload) ------------------------
    def put_stream(
        self,
        url: str,
        source: str | Path,
        *,
        offset: int = 0,
        length: int | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
        retries: int = 0,
    ) -> Response:
        """Отправить кусок файла методом PUT, не загружая его в память целиком.

        Нужно для докачки (YouTube resumable): сервер просит продолжить с
        определённого байта, и мы отправляем ровно этот кусок.
        """
        path = Path(source)
        total = path.stat().st_size
        if length is None:
            length = total - offset
        end = min(total, offset + length)
        if end <= offset:
            raise HTTPError(f"Пустой диапазон для {path}", url=url)

        def iterator() -> Iterable[bytes]:
            with path.open("rb") as fh:
                fh.seek(offset)
                remaining = end - offset
                while remaining > 0:
                    block = fh.read(min(4 * 1024 * 1024, remaining))
                    if not block:
                        break
                    remaining -= len(block)
                    yield block

        request_headers = {
            "User-Agent": USER_AGENT,
            "Content-Length": str(end - offset),
            "Content-Type": "application/octet-stream",
        }
        request_headers.update(headers or {})

        attempts = max(1, retries + 1)
        last: Exception | None = None
        for _attempt in range(attempts):
            request = urllib.request.Request(url, data=iterator(), headers=request_headers, method="PUT")
            try:
                with urllib.request.urlopen(request, timeout=timeout or max(self.timeout, 600)) as response:
                    payload = response.read(self.max_body)
                    return Response(
                        response.status,
                        payload,
                        {k.lower(): v for k, v in response.headers.items()},
                        response.geturl(),
                    )
            except urllib.error.HTTPError as exc:
                payload = b""
                try:
                    payload = exc.read(self.max_body) if exc.fp else b""
                except Exception:  # pragma: no cover
                    payload = b""
                return Response(
                    exc.code,
                    payload,
                    {k.lower(): v for k, v in (exc.headers or {}).items()},
                    url,
                )
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
                last = exc
        raise HTTPError(f"Не удалось отправить файл {path}: {last}", url=url)

    def download(self, url: str, destination: str | Path, *, timeout: float | None = None) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self.get(url, timeout=timeout or max(self.timeout, 300))
        if not response.ok:
            raise HTTPError(
                f"Не удалось скачать {url}: HTTP {response.status}",
                status=response.status,
                body=response.text[:500],
                url=url,
            )
        destination.write_bytes(response.body)
        return destination

    # -- вспомогательное ----------------------------------------------------
    def _wait(self, attempt: int, response: Response | None) -> None:
        delay = min(30.0, 1.5 * (2**attempt))
        if response is not None:
            retry_after = response.header("retry-after")
            if retry_after.isdigit():
                delay = min(60.0, float(retry_after))
            self.log(f"HTTP {response.status}, повтор через {delay:.0f} с")
        else:
            self.log(f"Сетевой сбой, повтор через {delay:.0f} с")
        self.sleep(delay)

    # -- проверки ответов ---------------------------------------------------
    @staticmethod
    def expect_ok(response: Response, what: str) -> Response:
        if response.ok:
            return response
        snippet = response.text[:600].replace("\n", " ")
        raise HTTPError(
            f"{what}: HTTP {response.status}. {snippet}",
            status=response.status,
            body=response.text,
            url=response.url,
        )

    @staticmethod
    def expect_json(response: Response, what: str) -> Any:
        HTTPClient.expect_ok(response, what)
        return response.json()


def chunked(items: Iterable[Any], size: int) -> Iterable[list[Any]]:
    """Разбить последовательность на куски по size элементов."""
    chunk: list[Any] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
