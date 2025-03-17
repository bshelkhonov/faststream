from typing import TYPE_CHECKING, Any, Callable, Iterable, cast

from fast_depends.utils import get_typed_annotation
from fastapi.dependencies.utils import get_dependant, get_parameterless_sub_dependant

from faststream._compat import PYDANTIC_V2

if TYPE_CHECKING:
    from fastapi import params
    from fastapi.dependencies.models import Dependant


def get_fastapi_dependant(
    orig_call: Callable[..., Any],
    dependencies: Iterable["params.Depends"],
) -> Any:
    """Generate FastStream-Compatible FastAPI Dependant object."""
    dependent = get_fastapi_native_dependant(
        orig_call=orig_call,
        dependencies=dependencies,
    )

    dependent = _patch_fastapi_dependent(dependent)

    return dependent


def get_fastapi_native_dependant(
    orig_call: Callable[..., Any],
    dependencies: Iterable["params.Depends"],
) -> Any:
    """Generate native FastAPI Dependant."""
    dependent = get_dependant(
        path="",
        call=orig_call,
    )

    for depends in list(dependencies)[::-1]:
        dependent.dependencies.insert(
            0,
            get_parameterless_sub_dependant(depends=depends, path=""),
        )

    return dependent


def _patch_fastapi_dependent(dependant: "Dependant") -> "Dependant":
    """Patch FastAPI by adding fields for AsyncAPI schema generation."""
    from pydantic import Field, create_model  # FastAPI always has pydantic

    from faststream._compat import PydanticUndefined

    params = dependant.query_params + dependant.body_params

    for d in dependant.dependencies:
        params.extend(d.query_params + d.body_params)

    params_unique = {}

    call = dependant.call
    if is_faststream_decorated(call):
        call = getattr(call, "__wrapped__", call)
    globalns = getattr(call, "__globals__", {})

    for p in params:
        if p.name not in params_unique:
            info: Any = p.field_info if PYDANTIC_V2 else p

            field_data = {
                "default": ... if info.default is PydanticUndefined else info.default,
                "default_factory": info.default_factory,
                "alias": info.alias,
            }

            if PYDANTIC_V2:
                from pydantic.fields import FieldInfo

                info = cast("FieldInfo", info)

                field_data.update(
                    {
                        "title": info.title,
                        "alias_priority": info.alias_priority,
                        "validation_alias": info.validation_alias,
                        "serialization_alias": info.serialization_alias,
                        "description": info.description,
                        "discriminator": info.discriminator,
                        "examples": info.examples,
                        "exclude": info.exclude,
                        "json_schema_extra": info.json_schema_extra,
                    }
                )

                f = next(
                    filter(
                        lambda x: isinstance(x, FieldInfo),
                        p.field_info.metadata or (),
                    ),
                    Field(**field_data),  # type: ignore[pydantic-field,unused-ignore]
                )

            else:
                from pydantic.fields import ModelField  # type: ignore[attr-defined]

                info = cast("ModelField", info)

                field_data.update(
                    {
                        "title": info.field_info.title,
                        "description": info.field_info.description,
                        "discriminator": info.field_info.discriminator,
                        "exclude": info.field_info.exclude,
                        "gt": info.field_info.gt,
                        "ge": info.field_info.ge,
                        "lt": info.field_info.lt,
                        "le": info.field_info.le,
                    }
                )
                f = Field(**field_data)  # type: ignore[pydantic-field,unused-ignore]

            params_unique[p.name] = (
                get_typed_annotation(info.annotation, globalns, {}),
                f,
            )

    dependant.model = create_model(  # type: ignore[attr-defined]
        getattr(call, "__name__", type(call).__name__)
    )

    dependant.custom_fields = {}  # type: ignore[attr-defined]
    dependant.flat_params = params_unique  # type: ignore[attr-defined]

    return dependant


FASTSTREAM_FASTAPI_PLUGIN_DECORATOR_MARKER = "__faststream_consumer__"


def is_faststream_decorated(func: object) -> bool:
    return getattr(func, FASTSTREAM_FASTAPI_PLUGIN_DECORATOR_MARKER, False)


def mark_faststream_decorated(func: object) -> None:
    setattr(func, FASTSTREAM_FASTAPI_PLUGIN_DECORATOR_MARKER, True)
