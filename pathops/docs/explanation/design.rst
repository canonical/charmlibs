.. meta::
   :description: Why pathops models charm filesystem operations on pathlib.

Design philosophy
=================

:mod:`pathops` provides a :mod:`pathlib`-like interface for working with files in both local and remote (Pebble-based) filesystems. This document explains the design choices behind the library.

A pathlib-like interface
------------------------

The core goal of ``pathops`` is to let charm authors write filesystem code once and have it work on both Kubernetes and machine charms. To achieve this, :class:`~pathops.ContainerPath` mirrors the :class:`pathlib.PurePosixPath` and :class:`pathlib.Path` APIs as closely as possible.

``pathlib`` has a familiar interface — the ``/`` operator for joining, :meth:`~pathlib.Path.read_text` and :meth:`~pathlib.Path.write_text` for file I/O, :meth:`~pathlib.Path.mkdir` for directory creation, :meth:`~pathlib.Path.glob` for matching. By matching ``pathlib``'s interface, ``pathops`` avoids introducing new concepts. Code that works with ``pathlib.Path`` should look almost identical when ported to ``ContainerPath``.

Where ``pathops`` diverges from ``pathlib``, it's because the underlying Pebble API imposes constraints:

- **No** ``open()`` **method.** Pebble's push/pull model doesn't map cleanly to Python file handles. Use :meth:`~pathlib.Path.read_text`, :meth:`~pathlib.Path.read_bytes`, :meth:`~pathlib.Path.write_text`, and :meth:`~pathlib.Path.write_bytes` instead.
- **Absolute paths only.** :class:`~pathops.ContainerPath` raises :class:`~pathops.RelativePathError` if you try to create a relative path, because Pebble operations require absolute paths.
- **No** ``chmod()`` **method.** Permissions are set at write time via ``mode=``, ``user=``, and ``group=`` keyword arguments on ``write_text()``, ``write_bytes()``, and ``mkdir()``. This matches Pebble's API, where permissions are part of the push/make_dir call.
- **Default file mode is 0o644**, not ``pathlib``'s 0o666. This matches Pebble's default and is a more sensible default for most use cases.

PathProtocol
------------

:class:`~pathops.PathProtocol` is a :class:`typing.Protocol` that defines the interface common to both :class:`~pathops.ContainerPath` and :class:`~pathops.LocalPath`. It exists so that charm authors can write helpers that accept either path type:

.. code-block:: python

   from charmlibs import pathops

   def write_config(root: pathops.PathProtocol, content: str) -> None:
       (root / 'etc' / 'myapp' / 'config.yaml').write_text(content)

You might think ``LocalPath | ContainerPath`` would work just as well, but in practice it's much less useful. A union type shows the *superset* of methods and arguments from both types in your IDE — including things like :class:`pathlib.PosixPath` methods that don't exist on :class:`~pathops.ContainerPath`. :class:`~pathops.PathProtocol` shows only the *subset* that both types support, so your IDE completions are exactly the methods you can safely call.

.. note::

   :class:`~pathops.PathProtocol` is not designed to be implemented by third parties. We don't guarantee compatibility for third-party implementations when we add new methods to the protocol. One example: adding a method to the protocol is only a minor version bump (it's a feature for users of the concrete classes), not a major one (it's a potentially breaking change for implementations of the protocol). Treat the protocol as a convenient type annotation for the ``pathops`` classes, not a compatibility guarantee for other implementations.

:class:`~pathops.LocalPath` is a concrete subclass of :class:`pathlib.PosixPath` that extends its write methods — :meth:`~pathlib.Path.write_text`, :meth:`~pathlib.Path.write_bytes`, and :meth:`~pathlib.Path.mkdir` — with ``mode=``, ``user=``, and ``group=`` keyword arguments for setting permissions and ownership at write time. This means it inherits all of ``pathlib``'s functionality while matching the permission-setting interface that :class:`~pathops.ContainerPath` uses. :class:`~pathops.PathProtocol` captures the subset of that functionality that both types share.
