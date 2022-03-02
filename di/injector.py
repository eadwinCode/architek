import typing as t
from inspect import isabstract
from injector import Injector, Binder as InjectorBinder, Binding
from starletteapi.context import ExecutionContext
from .scopes import DIScope, ScopeDecorator, TransientScope, SingletonScope, RequestScope
from .providers import InstanceProvider, Provider
from starletteapi.logger import logger as log

from starletteapi.helper import get_name

if t.TYPE_CHECKING:
    from starletteapi.main import StarletteApp
    from starletteapi.module import ApplicationModuleBase

T = t.TypeVar("T")


class DIRequestServiceProvider:
    __slots__ = ('injector', 'container', 'context', '_log_prefix')

    def __init__(self, container: 'Container', context: t.Optional[t.Dict]) -> None:
        self.injector = container.injector
        self.container = container
        self.context = context
        self._log_prefix = self.injector._log_prefix

    def get(self, interface: t.Type[T]) -> T:
        binding, binder = self.container.get_binding(interface)
        scope = binding.scope
        if isinstance(scope, ScopeDecorator):
            scope = scope.scope
        # Fetch the corresponding Scope instance from the Binder.
        scope_binding, _ = binder.get_binding(scope)
        scope_instance = t.cast(DIScope, scope_binding.provider.get(self))

        log.debug(
            '%StarletteInjector.get(%r, scope=%r) using %r', self._log_prefix, interface, scope,
            binding.provider
        )
        result = scope_instance.get(interface, binding.provider, context=self.context).get(self.injector)
        log.debug('%s -> %r', self._log_prefix, result)
        return result

    def update_context(self, interface: t.Type[T], value: T) -> None:
        if not isinstance(value, Provider):
            self.context.update({interface: InstanceProvider(value)})
        self.context.update({interface: value})


class Container(InjectorBinder):
    __slots__ = ('injector', '_auto_bind', '_bindings', 'parent')

    def create_binding(
            self, interface: type, to: t.Any = None, scope: t.Union[ScopeDecorator, t.Type[DIScope]] = None
    ) -> Binding:
        provider = self.provider_for(interface, to)
        scope = scope or getattr(to or interface, '__scope__', TransientScope)
        if isinstance(scope, ScopeDecorator):
            scope = scope.scope
        return Binding(interface, provider, scope)

    def add_binding(self, interface: t.Type, binding: Binding) -> None:
        self._bindings[interface] = binding

    def register(
            self,
            base_type: t.Type,
            concrete_type: t.Union[t.Type, None] = None,
            scope: t.Union[t.Type[DIScope], ScopeDecorator] = TransientScope
    ):
        try:
            assert issubclass(concrete_type, base_type), (
                f"Cannot register {get_name(base_type)} for abstract class "
                f"{get_name(concrete_type)}"
            )
        except TypeError:
            # ignore, this happens with generic types
            pass

        provider = self.provider_for(base_type, concrete_type)
        if isinstance(scope, ScopeDecorator):
            scope = scope.scope
        self.add_binding(base_type, Binding(base_type, provider, scope))

    def add_instance(
            self, instance: T,
            concrete_type: t.Optional[t.Type[T]] = None
    ) -> None:
        assert not isinstance(instance, type)
        concrete_type = instance.__class__ if not concrete_type else concrete_type
        self.register(concrete_type, instance)

    def add_singleton(self, base_type: t.Type[T], concrete_type: t.Optional[t.Type[T]] = None) -> None:
        if not concrete_type:
            self.add_exact_singleton(concrete_type)
        self.register(base_type, concrete_type, scope=SingletonScope)

    def add_transient(self, base_type: t.Type, concrete_type: t.Optional[t.Type] = None) -> None:
        if not concrete_type:
            self.add_exact_singleton(concrete_type)
        self.register(base_type, concrete_type, scope=TransientScope)

    def add_scoped(self, base_type: t.Type, concrete_type: t.Optional[t.Type] = None) -> None:
        if not concrete_type:
            self.add_exact_singleton(concrete_type)
        self.register(base_type, concrete_type, scope=TransientScope)

    def add_exact_singleton(self, concrete_type: t.Type[T]) -> None:
        assert not isabstract(concrete_type)
        self.register(base_type=concrete_type, scope=SingletonScope)

    def add_exact_transient(self, concrete_type: t.Type[T]) -> None:
        assert not isabstract(concrete_type)
        self.register(base_type=concrete_type, scope=TransientScope)

    def add_exact_scoped(self, concrete_type: t.Type[T], ) -> None:
        assert not isabstract(concrete_type)
        self.register(base_type=concrete_type, scope=RequestScope)


class StarletteInjector(Injector):
    __slots__ = ('_stack', 'parent', 'app', 'container',)

    def __init__(
            self,
            app: 'StarletteApp',
            auto_bind: bool = True,
            parent: 'Injector' = None,
    ):
        self._stack = ()

        self.parent = parent
        self.app = app
        # Binder
        self.container = Container(
            self, auto_bind=auto_bind, parent=parent.binder if parent is not None else None
        )
        # Bind some useful types
        self.container.add_instance(self, StarletteInjector)
        self.container.add_instance(self.binder)
        self.container.add_exact_scoped(ExecutionContext)

    @property
    def binder(self):
        return self.container

    @binder.setter
    def binder(self, value):
        ...

    def create_di_request_service_provider(self, context: t.Dict) -> DIRequestServiceProvider:
        return DIRequestServiceProvider(self.container, context)

    def initialize_root_module(self, *, root_module: t.Type['ApplicationModuleBase']):
        # Initialise modules
        self.container.install(root_module)
