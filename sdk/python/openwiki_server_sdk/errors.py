from __future__ import annotations


class OpenWikiServerError(Exception):
    """SDK 所有异常基类。"""


class OpenWikiServerTransportError(OpenWikiServerError):
    """传输层异常：连接、超时、非预期 HTTP 状态。"""

    def __init__(self, message: str, *, trace_id: str = "") -> None:
        super().__init__(message)
        self.trace_id = trace_id


class OpenWikiServerConnectionError(OpenWikiServerTransportError):
    """无法建立连接。"""


class OpenWikiServerTimeoutError(OpenWikiServerTransportError):
    """请求超时。"""


class OpenWikiServerProtocolError(OpenWikiServerTransportError):
    """响应不符合统一响应壳协议。"""


class OpenWikiServerHTTPStatusError(OpenWikiServerTransportError):
    """非 2xx 且无法解析统一响应壳。"""

    def __init__(self, message: str, *, status_code: int, body: str = "", trace_id: str = "") -> None:
        super().__init__(message, trace_id=trace_id)
        self.status_code = status_code
        self.body = body


class OpenWikiServerAPIError(OpenWikiServerError):
    """服务端返回统一响应壳但 errCode != 0。"""

    def __init__(self, message: str, *, err_code: str, err_msg: str, trace_id: str = "") -> None:
        super().__init__(message)
        self.err_code = err_code
        self.err_msg = err_msg
        self.trace_id = trace_id


class OpenWikiServerValidationError(OpenWikiServerAPIError):
    """参数校验失败（200001）。"""


class OpenWikiServerNotFoundError(OpenWikiServerAPIError):
    """资源不存在（200404）。"""


class OpenWikiServerConflictError(OpenWikiServerAPIError):
    """资源冲突（200409）。"""


class OpenWikiServerSystemError(OpenWikiServerAPIError):
    """服务端系统内部错误（200500）。"""


class OpenWikiServerBusinessError(OpenWikiServerAPIError):
    """其他业务错误码兜底。"""


_ERROR_CODE_CLASSES: dict[str, type[OpenWikiServerAPIError]] = {
    "200001": OpenWikiServerValidationError,
    "200404": OpenWikiServerNotFoundError,
    "200409": OpenWikiServerConflictError,
    "200500": OpenWikiServerSystemError,
}


def exception_from_code(err_code: str, err_msg: str, trace_id: str = "") -> OpenWikiServerAPIError:
    """按错误码生成对应异常；未知错误码映射为 OpenWikiServerBusinessError。"""
    error_class = _ERROR_CODE_CLASSES.get(err_code, OpenWikiServerBusinessError)
    return error_class(
        f"{err_code} {err_msg}".strip(), err_code=err_code, err_msg=err_msg, trace_id=trace_id
    )
