"""Abstract adapter interface for realtime vehicle position sources.

Populated in Phase 2 Step 3: defines the contract each source adapter
(IETT SOAP, Metro Istanbul, Marmaray tarife-based, etc.) must implement so
the Celery task pipeline can poll them uniformly.

TODO (Phase 2 Step 3): define BaseAdapter with fetch() → list[VehiclePosition].
"""
