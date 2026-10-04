"""Feishu (Lark / 飞书) channel.

The package is import-safe WITHOUT the optional ``lark-oapi`` dependency: the
SDK is imported lazily inside :mod:`junction.feishu.client` methods, so the
channel roster in :mod:`junction.channels` can import ``maybe_start_feishu``
on any build. See ``src/junction/docs/feishu-integration.md``.
"""
