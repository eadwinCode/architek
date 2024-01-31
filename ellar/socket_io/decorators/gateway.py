import typing as t

from ellar.common.compatible import AttributeDict
from ellar.common.exceptions import ImproperConfiguration
from ellar.di import RequestORTransientScope, injectable
from ellar.reflect import REFLECT_TYPE, reflect
from ellar.socket_io.constants import (
    GATEWAY_METADATA,
    GATEWAY_OPTIONS,
    GATEWAY_WATERMARK,
)
from ellar.socket_io.model import GatewayBase, GatewayType
from ellar.utils import get_name, get_type_of_base


def WebSocketGateway(
    path: str = "/socket.io", name: t.Optional[str] = None, **kwargs: str
) -> t.Callable:
    kwargs.setdefault("async_mode", "asgi")
    kwargs.setdefault("cors_allowed_origins", "*")

    def _decorator(cls: t.Type) -> t.Type:
        assert path == "" or path.startswith("/"), "Routed paths must start with '/'"
        _kwargs = AttributeDict(
            socket_init_kwargs=dict(kwargs),
            path=path,
            name=name,
            include_in_schema=False,
            processed=False,
        )

        if not isinstance(cls, type):
            raise ImproperConfiguration(
                f"WebSocketGateway is a class decorator - {cls}"
            )

        _gateway_type = t.cast(t.Type[GatewayBase], cls)
        new_cls = None

        if type(_gateway_type) is not GatewayType:
            # We force the cls to inherit from `ControllerBase` by creating another type.
            attrs = {}
            if hasattr(cls, REFLECT_TYPE):
                attrs.update({REFLECT_TYPE: cls.__dict__[REFLECT_TYPE]})
            new_cls = type(cls.__name__, (cls, GatewayBase), attrs)

            _gateway_type = t.cast(t.Type[GatewayBase], new_cls)

        if not _kwargs["name"]:
            _kwargs["name"] = (
                str(get_name(_gateway_type)).lower().replace("gateway", "")
            )

        for base in get_type_of_base(GatewayBase, _gateway_type):
            if reflect.has_metadata(GATEWAY_WATERMARK, base) and hasattr(
                _gateway_type, "__GATEWAY_WATERMARK__"
            ):
                raise ImproperConfiguration(
                    f"`@WebSocketGateway` decorated classes does not support inheritance. \n"
                    f"{_gateway_type}"
                )

        if not reflect.has_metadata(GATEWAY_WATERMARK, _gateway_type) and not hasattr(
            _gateway_type, "__GATEWAY_WATERMARK__"
        ):
            reflect.define_metadata(GATEWAY_WATERMARK, True, _gateway_type)
            reflect.define_metadata(
                GATEWAY_OPTIONS, _kwargs["socket_init_kwargs"], _gateway_type
            )

            injectable(RequestORTransientScope)(_gateway_type)

            for key in GATEWAY_METADATA.keys:
                reflect.define_metadata(key, _kwargs[key], _gateway_type)

        if new_cls:
            _gateway_type.__GATEWAY_WATERMARK__ = True  # type:ignore[attr-defined]

        return _gateway_type

    if callable(path):
        func = path
        path = "/socket.io"
        return _decorator(func)  # type:ignore[arg-type]
    return _decorator
