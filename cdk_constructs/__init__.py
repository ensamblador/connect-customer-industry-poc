"""cdk_constructs — shared, industry-agnostic CDK constructs and helpers.

Every construct here is parameterized (no ambient ``import config``): the
per-industry apps pass their own values in from their local ``config.py``.
Editing a module here changes behavior for every industry app that imports it.
"""
