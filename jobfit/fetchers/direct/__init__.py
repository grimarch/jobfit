"""Direct fetchers — go straight to source, not via jobhive aggregator."""

from jobfit.fetchers.direct import bundesagentur, everjobs, softgarden

__all__ = ["bundesagentur", "everjobs", "softgarden"]
